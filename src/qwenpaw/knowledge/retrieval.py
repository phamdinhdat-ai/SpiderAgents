# -*- coding: utf-8 -*-
"""Cross-document retrieval, reranking, and multi-source result merging.

Provides:
- :class:`CrossDocumentRetriever` — multi-doc search with per-doc grouping
- Reciprocal Rank Fusion (RRF) for merging results from multiple sources
- MCP result integration for external knowledge sources
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .models import KnowledgeDocument, SearchResult

logger = logging.getLogger(__name__)


class CrossDocumentRetriever:
    """Retrieves and merges results across multiple documents.

    Wraps a :class:`KnowledgeBaseManager` to provide cross-document
    retrieval strategies and result fusion.

    Args:
        kb_manager: The owning knowledge base manager.
    """

    def __init__(self, kb_manager: Any) -> None:
        self._kb = kb_manager

    async def retrieve_multi(
        self,
        query: str,
        top_k_per_doc: int = 3,
        kb_names: list[str] | None = None,
    ) -> dict[str, list[SearchResult]]:
        """Search each document independently and group results.

        Args:
            query: Search query.
            top_k_per_doc: Max results per document.
            kb_names: Optional KB filter.

        Returns:
            Dict mapping ``document_id`` → list of results.
        """
        # Get a broad candidate pool first
        candidates = await self._kb.search(
            query=query,
            top_k=50,  # wide net
            kb_names=kb_names,
        )

        # Group by document and take top_k_per_doc from each
        grouped: dict[str, list[SearchResult]] = {}
        for result in candidates:
            grouped.setdefault(result.document_id, []).append(result)

        for doc_id in grouped:
            grouped[doc_id].sort(key=lambda r: r.score, reverse=True)
            grouped[doc_id] = grouped[doc_id][:top_k_per_doc]

        return grouped

    async def merge_and_rerank(
        self,
        results: list[SearchResult],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Re-rank a list of search results by relevance.

        Currently uses a simple score-sort. Future enhancements may
        include cross-encoder reranking.

        Args:
            results: Flat list of search results.
            top_k: Number of top results to return.

        Returns:
            Top *top_k* results sorted by descending score.
        """
        # Deduplicate by chunk_id (keep highest score)
        seen: dict[str, SearchResult] = {}
        for r in results:
            if r.chunk_id not in seen or r.score > seen[r.chunk_id].score:
                seen[r.chunk_id] = r

        deduped = sorted(
            seen.values(),
            key=lambda r: r.score,
            reverse=True,
        )
        return deduped[:top_k]

    @staticmethod
    def reciprocal_rank_fusion(
        result_sets: list[list[SearchResult]],
        k: int = 60,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Combine multiple ranked result lists using RRF.

        Each result's RRF score is::

            sum(1 / (k + rank_i)) for each list i where the result appears

        Args:
            result_sets: One ranked list per source / retriever.
            k: RRF smoothing constant (default 60).
            top_k: Number of fused results to return.

        Returns:
            Fused and ranked results, with ``score`` representing
            the RRF score (not a cosine similarity).
        """
        rrf_scores: dict[str, tuple[float, SearchResult]] = {}

        for result_list in result_sets:
            for rank, result in enumerate(result_list, start=1):
                key = result.chunk_id
                rrf_score = 1.0 / (k + rank)
                if key in rrf_scores:
                    old_score, old_result = rrf_scores[key]
                    rrf_scores[key] = (
                        old_score + rrf_score,
                        old_result,  # keep first occurrence
                    )
                else:
                    rrf_scores[key] = (rrf_score, result)

        # Sort by RRF score descending
        fused = sorted(
            rrf_scores.values(),
            key=lambda x: x[0],
            reverse=True,
        )
        top = fused[:top_k]

        # Update result scores to RRF values
        for rrf_score, result in top:
            result.score = rrf_score
        return [r for _, r in top]

    async def retrieve_from_all_sources(
        self,
        query: str,
        top_k: int = 5,
        kb_names: list[str] | None = None,
    ) -> list[SearchResult]:
        """Retrieve from local KB and all registered MCP sources.

        Queries the local knowledge base and any external MCP tools
        registered for knowledge retrieval, then merges all results
        using RRF.

        Args:
            query: Search query.
            top_k: Number of final merged results.
            kb_names: Optional KB filter.

        Returns:
            Merged and reranked results from all available sources.
        """
        result_sets: list[list[SearchResult]] = []

        # 1. Local KB
        try:
            local_results = await self._kb.search(
                query=query,
                top_k=top_k * 3,
                kb_names=kb_names,
            )
            if local_results:
                result_sets.append(local_results)
        except Exception as exc:
            logger.warning("Local KB search failed: %s", exc)

        # 2. MCP external tools (discovered via agent's MCP clients)
        try:
            mcp_results = await self._search_mcp_sources(query, top_k)
            if mcp_results:
                result_sets.append(mcp_results)
        except Exception as exc:
            logger.debug("MCP source search skipped or failed: %s", exc)

        if not result_sets:
            return []

        if len(result_sets) == 1:
            return result_sets[0][:top_k]

        # Fuse via RRF
        return self.reciprocal_rank_fusion(
            result_sets,
            k=60,
            top_k=top_k,
        )

    async def generate_cross_reference(
        self,
        chunks: list[SearchResult],
    ) -> list[dict[str, Any]]:
        """Detect overlapping topics across documents among *chunks*.

        Returns a list of cross-reference dicts with keys:
        ``document_a``, ``document_b``, ``shared_topic``,
        ``overlap_score``.

        This is a simple keyword-overlap heuristic; future versions
        may use embedding similarity.
        """
        from collections import Counter

        refs: list[dict[str, Any]] = []
        docs: list[tuple[str, str, set[str]]] = []
        for chunk in chunks:
            words = set(chunk.text.lower().split())
            docs.append((chunk.document_id, chunk.filename, words))

        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                doc_id_a, name_a, words_a = docs[i]
                doc_id_b, name_b, words_b = docs[j]
                if doc_id_a == doc_id_b:
                    continue

                shared = words_a & words_b
                # Remove stopwords-ish short words
                shared = {w for w in shared if len(w) > 3}
                if len(shared) < 3:
                    continue

                overlap = len(shared) / min(len(words_a), len(words_b))
                shared_topics = ", ".join(
                    sorted(shared, key=lambda w: -len(w))[:5],
                )
                refs.append(
                    {
                        "document_a": name_a,
                        "document_b": name_b,
                        "shared_topic": shared_topics,
                        "overlap_score": round(overlap, 2),
                    },
                )

        refs.sort(key=lambda r: r["overlap_score"], reverse=True)
        return refs

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _search_mcp_sources(
        self,
        query: str,
        top_k: int,
    ) -> list[SearchResult]:
        """Search all registered MCP retrieval tools.

        Discovers MCP tools whose names indicate knowledge retrieval
        capability (e.g., ``*search*``, ``*retrieve*``, ``*lookup*``)
        and queries them in parallel.
        """
        # Try to discover MCP tools from the agent's runner
        try:
            mcp_tools = await self._discover_mcp_retrieval_tools()
        except Exception:
            return []

        if not mcp_tools:
            return []

        # Query all MCP tools in parallel
        tasks = []
        for tool in mcp_tools:
            tasks.append(self._call_mcp_tool(tool, query, top_k))

        results_per_tool = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[SearchResult] = []
        for result in results_per_tool:
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, Exception):
                logger.debug("MCP tool call failed: %s", result)

        return all_results

    async def _discover_mcp_retrieval_tools(self) -> list[Any]:
        """Find MCP tools that support knowledge retrieval."""
        retrieval_keywords = [
            "search", "retrieve", "lookup", "query", "find",
            "knowledge", "document", "wiki", "rag",
        ]
        try:
            # Access MCP manager via workspace chain
            mcp_manager = getattr(self._kb, "_mcp_manager", None)
            if mcp_manager is None:
                # Try workspace → mcp_manager
                return []

            tools = []
            for client_name, client in mcp_manager._clients.items():
                try:
                    tool_list = await client.list_tools()
                    for tool in tool_list:
                        name_lower = tool.name.lower() if hasattr(tool, 'name') else str(tool).lower()
                        if any(kw in name_lower for kw in retrieval_keywords):
                            tools.append((client_name, tool))
                except Exception:
                    continue
            return tools
        except Exception:
            return []

    async def _call_mcp_tool(
        self,
        tool_info: tuple[str, Any],
        query: str,
        top_k: int,
    ) -> list[SearchResult]:
        """Call an MCP retrieval tool and parse results."""
        client_name, tool = tool_info
        try:
            tool_name = tool.name if hasattr(tool, 'name') else str(tool)
            mcp_manager = getattr(self._kb, "_mcp_manager", None)
            if mcp_manager is None:
                return []

            result = await mcp_manager.call_tool(
                client_name=client_name,
                tool_name=tool_name,
                arguments={"query": query, "max_results": top_k},
            )

            # Parse result into SearchResults
            return self._parse_mcp_result(result, tool_name)
        except Exception as exc:
            logger.debug("MCP tool %s failed: %s", getattr(tool, 'name', '?'), exc)
            return []

    @staticmethod
    def _parse_mcp_result(
        raw_result: Any,
        source_name: str,
    ) -> list[SearchResult]:
        """Parse a raw MCP tool result into SearchResult objects."""
        results: list[SearchResult] = []

        # Try structured content extraction
        content = None
        if hasattr(raw_result, "content"):
            content = raw_result.content
        elif isinstance(raw_result, list):
            content = raw_result
        elif isinstance(raw_result, dict):
            content = raw_result.get("content", [raw_result])
        else:
            content = [{"type": "text", "text": str(raw_result)}]

        if not isinstance(content, list):
            content = [content]

        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    results.append(
                        SearchResult(
                            document_id=f"mcp:{source_name}",
                            filename=f"External: {source_name}",
                            text=text[:500],
                            score=0.5,
                            chunk_id=f"mcp_{source_name}",
                        ),
                    )

        return results
