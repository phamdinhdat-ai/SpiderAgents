# -*- coding: utf-8 -*-
"""Vector store abstraction for knowledge base document storage.

Provides pluggable backends:
- :class:`ChromaVectorStore` — ChromaDB-backed (requires ``chromadb``)
- :class:`LocalVectorStore` — NumPy-based local store (Windows fallback)
"""

from __future__ import annotations

import json
import logging
import math
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import aiofiles

from .models import DocumentChunk, SearchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class VectorStore(ABC):
    """Abstract vector store for knowledge base chunks.

    Each store instance manages chunks for a single knowledge base
    within a workspace.
    """

    @abstractmethod
    async def start(self) -> None:
        """Initialize and connect to the backend."""

    @abstractmethod
    async def close(self) -> None:
        """Flush and release backend resources."""

    @abstractmethod
    async def add(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Index *chunks* with their pre-computed *embeddings*.

        Returns the number of chunks added.
        """

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_kb_names: list[str] | None = None,
    ) -> list[SearchResult]:
        """Return the *top_k* chunks most similar to *query_embedding*."""

    @abstractmethod
    async def delete(self, document_id: str) -> int:
        """Remove all chunks belonging to *document_id*.

        Returns the number of chunks removed.
        """

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of stored chunks."""


# ---------------------------------------------------------------------------
# ChromaDB backend
# ---------------------------------------------------------------------------


class ChromaVectorStore(VectorStore):
    """Vector store backed by ChromaDB.

    Creates a persistent collection per knowledge base under
    ``db_path``.
    """

    def __init__(
        self,
        collection_name: str,
        db_path: str,
    ) -> None:
        self._collection_name = collection_name
        self._db_path = db_path
        self._client: Any = None
        self._collection: Any = None

    async def start(self) -> None:
        """Connect to ChromaDB and get or create the collection."""
        try:
            import chromadb
        except ImportError:
            raise RuntimeError(
                "chromadb is required for ChromaVectorStore. "
                "Install it: pip install chromadb",
            ) from None

        os.makedirs(self._db_path, exist_ok=True)
        # Offload sync Chroma init to thread so it doesn't block the loop.
        import asyncio

        def _init():
            self._client = chromadb.PersistentClient(path=self._db_path)
            # Delete and recreate if exists to avoid dimension mismatch
            # after config changes.  Production systems would use a
            # distance-function-aware migration instead.
            try:
                self._client.delete_collection(self._collection_name)
            except Exception:
                pass
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        await asyncio.to_thread(_init)
        logger.info(
            "ChromaVectorStore ready: collection=%s db=%s",
            self._collection_name,
            self._db_path,
        )

    async def close(self) -> None:
        """ChromaDB client does not need explicit close."""
        self._collection = None
        self._client = None

    async def add(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Index chunks in ChromaDB."""
        if not chunks:
            return 0

        import asyncio

        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number or -1,
            }
            for c in chunks
        ]

        def _add():
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

        await asyncio.to_thread(_add)
        return len(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_kb_names: list[str] | None = None,
    ) -> list[SearchResult]:
        """Semantic search via ChromaDB."""
        import asyncio

        def _search():
            return self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

        results = await asyncio.to_thread(_search)

        search_results: list[SearchResult] = []
        if not results["ids"] or not results["ids"][0]:
            return search_results

        for i, chunk_id in enumerate(results["ids"][0]):
            doc_text = results["documents"][0][i]
            meta = results["metadatas"][0][i] or {}
            # Chroma returns cosine *distance*; convert to similarity score
            distance = results["distances"][0][i]
            score = 1.0 - (distance / 2.0)  # normalize cosine distance → [0,1]
            score = max(0.0, min(1.0, score))

            search_results.append(
                SearchResult(
                    document_id=meta.get("document_id", ""),
                    filename=meta.get("filename", ""),
                    text=doc_text,
                    score=score,
                    chunk_id=chunk_id,
                    page_number=(
                        int(meta["page_number"])
                        if meta.get("page_number", -1) >= 0
                        else None
                    ),
                ),
            )

        return search_results

    async def delete(self, document_id: str) -> int:
        """Delete chunks by document_id metadata filter."""
        import asyncio

        def _delete():
            # ChromaDB doesn't support delete-by-metadata natively,
            # so we query first, then delete by IDs.
            existing = self._collection.get(
                where={"document_id": document_id},
            )
            if existing["ids"]:
                self._collection.delete(ids=existing["ids"])
            return len(existing["ids"])

        return await asyncio.to_thread(_delete)

    async def count(self) -> int:
        """Return total chunks in the collection."""
        import asyncio

        def _count():
            return self._collection.count()

        return await asyncio.to_thread(_count)


# ---------------------------------------------------------------------------
# Local / NumPy backend (Windows fallback)
# ---------------------------------------------------------------------------


class LocalVectorStore(VectorStore):
    """Simple local vector store using in-memory NumPy arrays.

    Persists chunks and embeddings to a JSON file for durability.
    Suitable for small-to-medium knowledge bases on Windows where
    ChromaDB may not be available.
    """

    def __init__(
        self,
        collection_name: str,
        db_path: str,
    ) -> None:
        self._collection_name = collection_name
        self._db_path = Path(db_path)
        self._data_path = self._db_path / f"{collection_name}.json"
        self._embeddings: list[list[float]] = []
        self._chunks: list[DocumentChunk] = []

    async def start(self) -> None:
        """Load persisted data from disk."""
        self._db_path.mkdir(parents=True, exist_ok=True)
        if self._data_path.exists():
            try:
                async with aiofiles.open(
                    self._data_path, encoding="utf-8"
                ) as f:
                    data = json.loads(await f.read())
                self._embeddings = data.get("embeddings", [])
                self._chunks = [
                    DocumentChunk(**c) for c in data.get("chunks", [])
                ]
                logger.info(
                    "LocalVectorStore loaded %d chunks from %s",
                    len(self._chunks),
                    self._data_path,
                )
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning(
                    "Corrupt local store, starting fresh: %s", exc,
                )
                self._embeddings = []
                self._chunks = []

    async def close(self) -> None:
        """Persist to disk."""
        await self._save()

    async def add(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Add chunks to the in-memory store and persist."""
        self._chunks.extend(chunks)
        self._embeddings.extend(embeddings)
        await self._save()
        return len(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_kb_names: list[str] | None = None,
    ) -> list[SearchResult]:
        """Cosine-similarity search over in-memory vectors."""
        import asyncio

        if not self._embeddings:
            return []

        # Offload to thread — cosine over many vectors can be CPU-heavy.
        def _compute():
            scores = [
                self._cosine_similarity(query_embedding, emb)
                for emb in self._embeddings
            ]
            # Get top-k indices
            indexed = list(enumerate(scores))
            indexed.sort(key=lambda x: x[1], reverse=True)
            top = indexed[:top_k]

            results: list[SearchResult] = []
            for idx, score in top:
                if score <= 0.0:
                    continue
                chunk = self._chunks[idx]
                results.append(
                    SearchResult(
                        document_id=chunk.document_id,
                        filename="",
                        text=chunk.text,
                        score=score,
                        chunk_id=chunk.chunk_id,
                        page_number=chunk.page_number,
                    ),
                )
            return results

        return await asyncio.to_thread(_compute)

    async def delete(self, document_id: str) -> int:
        """Remove chunks for a document."""
        removed = 0
        keep_chunks: list[DocumentChunk] = []
        keep_embs: list[list[float]] = []
        for chunk, emb in zip(self._chunks, self._embeddings):
            if chunk.document_id == document_id:
                removed += 1
            else:
                keep_chunks.append(chunk)
                keep_embs.append(emb)
        self._chunks = keep_chunks
        self._embeddings = keep_embs
        if removed:
            await self._save()
        return removed

    async def count(self) -> int:
        """Return total chunk count."""
        return len(self._chunks)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def _save(self) -> None:
        """Persist current state to JSON."""
        import asyncio

        def _write():
            data = {
                "embeddings": self._embeddings,
                "chunks": [c.model_dump() for c in self._chunks],
            }
            self._db_path.mkdir(parents=True, exist_ok=True)
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

        await asyncio.to_thread(_write)
