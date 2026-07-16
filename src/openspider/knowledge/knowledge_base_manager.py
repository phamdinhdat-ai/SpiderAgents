# -*- coding: utf-8 -*-
"""Knowledge base manager — the core workspace service for document RAG.

Lifecycle mirrors :class:`BaseMemoryManager`:
1. Instantiate with ``working_dir`` and ``agent_id``.
2. ``await start()`` — initialise vector store and embedding model.
3. Use :meth:`ingest_document`, :meth:`knowledge_base_search`, etc.
4. ``await close()`` — flush and release resources.

Registers a ``knowledge_base_search`` tool for agents via
:meth:`list_kb_tools`, matching the pattern used by
:class:`ReMeLightMemoryManager`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from .chunker import TextChunker
from .models import (
    DocumentChunk,
    DocumentStatus,
    IndexingStatus,
    KnowledgeBaseInfo,
    KnowledgeDocument,
    SearchResult,
)
from .vector_store import ChromaVectorStore, LocalVectorStore, VectorStore

logger = logging.getLogger(__name__)

# Prompt injected into the agent's system prompt (pattern:
# BaseMemoryManager.get_memory_prompt).
KB_GUIDANCE_PROMPT_EN = """\
## Knowledge Base

You have access to a knowledge base containing uploaded documents
(PDFs, spreadsheets, Word documents, markdown files, and more).

### When to Use `knowledge_base_search`

- The user asks about content from uploaded documents or files.
- The user references a document by name.
- The user asks a factual question whose answer may be in the
  knowledge base — **check the KB first**, then fall back to your
  training data if nothing is found.
- The user asks for cross-document comparisons or multi-document
  analysis.
- The user says "search my documents", "find in my files", etc.

### How to Use

Call `knowledge_base_search(query="...")` with a specific, keyword-rich
search query. The tool returns the most relevant text chunks with their
source filenames and relevance scores.
"""

KB_GUIDANCE_PROMPT_ZH = """\
## 知识库

你可以访问包含已上传文档的知识库（PDF、电子表格、Word 文档、Markdown 文件等）。

### 何时使用 `knowledge_base_search`

- 用户询问关于已上传文档或文件的内容。
- 用户提到某个文档的名称。
- 用户提出一个事实性问题，答案可能在知识库中 — **先搜索知识库**，如果没找到再使用训练数据。
- 用户要求跨文档比较或多文档分析。
- 用户说"搜索我的文档"、"在我的文件中查找"等。

### 如何使用

调用 `knowledge_base_search(query="...")` 并使用具体、关键词丰富的搜索查询。
该工具返回最相关的文本片段及其源文件名和相关性分数。
"""

KB_GUIDANCE_PROMPT_VI = """\
## Kho Kiến Thức

Bạn có quyền truy cập vào kho kiến thức chứa các tài liệu đã tải lên
(PDF, bảng tính, tài liệu Word, tệp markdown, v.v.).

### Khi nào sử dụng `knowledge_base_search`

- Người dùng hỏi về nội dung từ các tài liệu hoặc tệp đã tải lên.
- Người dùng tham chiếu đến một tài liệu theo tên.
- Người dùng đặt câu hỏi thực tế mà câu trả lời có thể có trong
  kho kiến thức — **kiểm tra KB trước**, sau đó mới dùng dữ liệu
  huấn luyện nếu không tìm thấy.
- Người dùng yêu cầu so sánh chéo tài liệu hoặc phân tích đa tài liệu.
- Người dùng nói "tìm kiếm tài liệu của tôi", "tìm trong tệp", v.v.

### Cách sử dụng

Gọi `knowledge_base_search(query="...")` với truy vấn cụ thể, giàu từ
khóa. Công cụ trả về các đoạn văn bản liên quan nhất kèm tên tệp
nguồn và điểm liên quan.
"""

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".xlsx", ".xlsm", ".md", ".markdown",
    ".txt", ".log", ".csv", ".tsv",
})
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_PAGES = 500
KB_STORE_VERSION = "v1"


class KnowledgeBaseManager:
    """Workspace-level service for knowledge base operations.

    Manages document ingestion, embedding, semantic search, and
    agent-tool integration for a single agent workspace.

    Args:
        working_dir: Agent workspace root directory.
        agent_id: Unique agent identifier.
    """

    def __init__(self, working_dir: str, agent_id: str) -> None:
        self.working_dir = Path(working_dir)
        self.agent_id = agent_id
        self._started = False

        # Sub-directories
        self.kb_root = self.working_dir / "knowledge_base"
        self._files_dir = self.kb_root / "files"
        self._store_dir = self.kb_root / "store"
        self._registry_path = self.kb_root / "documents.json"

        # Lazy-initialised
        self._vector_store: VectorStore | None = None
        self._chunker: TextChunker | None = None
        self._embedding_fn: Any = None  # callable: text → embedding
        self._document_registry: dict[str, KnowledgeDocument] = {}
        self._embedding_config: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise directories, load registry, start vector store."""
        if self._started:
            return

        self._ensure_dirs()
        self._load_registry()

        # Resolve embedding config (reuse pattern from ReMeLightMemoryManager)
        self._embedding_config = self._get_embedding_config()

        # Create chunker from agent config
        chunk_cfg = self._get_kb_config()
        self._chunker = TextChunker(
            chunk_size=chunk_cfg.get("chunk_size", 500),
            chunk_overlap=chunk_cfg.get("chunk_overlap", 50),
        )

        # Choose vector store backend
        backend = self._detect_store_backend()
        collection = f"kb_{self.agent_id}"
        store_path = str(self._store_dir)

        if backend == "chroma":
            self._vector_store = ChromaVectorStore(collection, store_path)
        else:
            self._vector_store = LocalVectorStore(collection, store_path)

        await self._vector_store.start()

        # Initialise embedder
        await self._init_embedder()

        # Mark ready
        sentinel = self.kb_root / f".kb_store_{KB_STORE_VERSION}"
        sentinel.touch(exist_ok=True)

        self._started = True
        logger.info(
            "KnowledgeBaseManager started: agent=%s backend=%s docs=%d",
            self.agent_id,
            backend,
            len(self._document_registry),
        )

    async def close(self) -> None:
        """Persist registry and close vector store."""
        if not self._started:
            return
        self._save_registry()
        if self._vector_store is not None:
            await self._vector_store.close()
            self._vector_store = None
        self._started = False
        logger.info("KnowledgeBaseManager closed: agent=%s", self.agent_id)

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        file_path: Path,
        kb_name: str = "default",
    ) -> KnowledgeDocument:
        """Parse, chunk, embed, and store a document.

        Args:
            file_path: Path to the source file (will be copied into KB
                storage).
            kb_name: Named knowledge base (default ``"default"``).

        Returns:
            :class:`KnowledgeDocument` with the indexing result.
        """
        if not file_path.is_file():
            raise FileNotFoundError(f"Document not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )

        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File too large: {file_size} bytes "
                f"(max {MAX_FILE_SIZE_BYTES})",
            )

        # Create document record
        doc_id = uuid.uuid4().hex
        stored_name = f"{doc_id}_{file_path.name}"
        stored_path = self._files_dir / stored_name

        doc = KnowledgeDocument(
            id=doc_id,
            filename=file_path.name,
            file_path=str(stored_path),
            kb_name=kb_name,
            mime_type=self._guess_mime(file_path),
            size=file_size,
            status=DocumentStatus.INDEXING,
        )
        self._document_registry[doc_id] = doc
        self._save_registry()

        # Copy file into KB storage
        shutil.copy2(str(file_path), str(stored_path))

        try:
            # Parse → chunk → embed → store
            if self._chunker is None:
                raise RuntimeError("Chunker not initialized")

            chunks = self._chunker.chunk_document(stored_path, doc_id)
            if not chunks:
                raise ValueError("Document produced no text content")

            # Embed all chunks
            chunk_texts = [c.text for c in chunks]
            embeddings = await self._embed_texts(chunk_texts)

            # Store in vector DB
            if self._vector_store is None:
                raise RuntimeError("Vector store not initialized")
            await self._vector_store.add(chunks, embeddings)

            doc.status = DocumentStatus.READY
            doc.chunk_count = len(chunks)
        except Exception as exc:
            doc.status = DocumentStatus.ERROR
            doc.error_message = str(exc)
            logger.exception(
                "Failed to index document %s: %s", file_path.name, exc,
            )

        doc.metadata["last_indexed"] = datetime.now(timezone.utc).isoformat()
        self._save_registry()
        return doc

    async def remove_document(self, document_id: str) -> bool:
        """Delete a document and its vector chunks.

        Returns ``True`` if the document was found and removed.
        """
        doc = self._document_registry.pop(document_id, None)
        if doc is None:
            return False

        # Remove from vector store
        if self._vector_store is not None:
            await self._vector_store.delete(document_id)

        # Remove stored file
        stored = Path(doc.file_path)
        try:
            if stored.exists():
                stored.unlink()
        except OSError:
            pass

        self._save_registry()
        return True

    async def list_documents(
        self,
        kb_name: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List all documents, optionally filtered by knowledge base."""
        docs = list(self._document_registry.values())
        if kb_name is not None:
            docs = [d for d in docs if d.kb_name == kb_name]
        docs.sort(key=lambda d: d.created_at, reverse=True)
        return docs

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        """Get a single document by ID."""
        return self._document_registry.get(document_id)

    async def get_indexing_status(self, kb_name: str = "default") -> IndexingStatus:
        """Return aggregate indexing status for a knowledge base."""
        docs = await self.list_documents(kb_name=kb_name)
        status = IndexingStatus(kb_name=kb_name, total_documents=len(docs))
        for doc in docs:
            status.total_chunks += doc.chunk_count
            if doc.status == DocumentStatus.READY:
                status.ready_count += 1
            elif doc.status == DocumentStatus.INDEXING:
                status.indexing_count += 1
            elif doc.status == DocumentStatus.PENDING:
                status.pending_count += 1
            elif doc.status == DocumentStatus.ERROR:
                status.error_count += 1
        status.documents = docs
        return status

    async def list_knowledge_bases(self) -> list[KnowledgeBaseInfo]:
        """List all named knowledge bases with summary stats."""
        groups: dict[str, list[KnowledgeDocument]] = {}
        for doc in self._document_registry.values():
            groups.setdefault(doc.kb_name, []).append(doc)

        infos: list[KnowledgeBaseInfo] = []
        for name, docs in groups.items():
            ready_docs = [d for d in docs if d.status == DocumentStatus.READY]
            infos.append(
                KnowledgeBaseInfo(
                    name=name,
                    document_count=len(ready_docs),
                    total_chunks=sum(d.chunk_count for d in ready_docs),
                    created_at=min(
                        (d.created_at for d in docs),
                        default=datetime.now(timezone.utc).isoformat(),
                    ),
                ),
            )
        infos.sort(key=lambda i: i.name)
        return infos

    async def reindex_all(self, kb_name: str = "default") -> dict[str, Any]:
        """Clear and re-index all documents in *kb_name*.

        Returns a summary dict with counts.
        """
        docs = await self.list_documents(kb_name=kb_name)
        # Delete all vectors
        for doc in docs:
            if self._vector_store is not None:
                await self._vector_store.delete(doc.id)

        # Re-ingest each document
        succeeded = 0
        failed = 0
        for doc in docs:
            try:
                stored = Path(doc.file_path)
                if stored.exists():
                    await self.ingest_document(stored, kb_name=kb_name)
                    succeeded += 1
                else:
                    doc.status = DocumentStatus.ERROR
                    doc.error_message = "Source file missing"
                    failed += 1
            except Exception as exc:
                doc.status = DocumentStatus.ERROR
                doc.error_message = str(exc)
                failed += 1

        self._save_registry()
        return {"total": len(docs), "succeeded": succeeded, "failed": failed}

    # ------------------------------------------------------------------
    # Search (synchronous tool interface)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 5,
        kb_names: list[str] | None = None,
    ) -> list[SearchResult]:
        """Semantic search across all indexed documents."""
        if self._vector_store is None:
            return []

        # Tokenize query (CJK-aware, same logic as ReMeLightMemoryManager)
        query_tokens = " ".join(self._tokenize_query(query))

        # Get query embedding
        embedding = await self._embed_text(query_tokens)

        # Vector search
        results = await self._vector_store.search(
            embedding,
            top_k=top_k,
            filter_kb_names=kb_names,
        )

        # Enrich results with document metadata
        for r in results:
            doc = self._document_registry.get(r.document_id)
            if doc is not None:
                r.filename = doc.filename
                r.kb_name = doc.kb_name

        return results

    # ------------------------------------------------------------------
    # Agent tool integration
    # ------------------------------------------------------------------

    def list_kb_tools(self) -> list:
        """Return tool functions to register with the agent toolkit.

        Pattern matches :meth:`BaseMemoryManager.list_memory_tools`.
        """
        return [self.knowledge_base_search]

    def get_kb_prompt(self, language: str = "en") -> str:
        """Return KB guidance for injection into the system prompt.

        Pattern matches :meth:`BaseMemoryManager.get_memory_prompt`.
        """
        prompts = {
            "zh": KB_GUIDANCE_PROMPT_ZH,
            "en": KB_GUIDANCE_PROMPT_EN,
            "vi": KB_GUIDANCE_PROMPT_VI,
        }
        return prompts.get(language, KB_GUIDANCE_PROMPT_EN)

    async def knowledge_base_search(
        self,
        query: str,
        max_results: int = 5,
        min_score: float = 0.1,
    ) -> ToolResponse:
        """Search the knowledge base for relevant document chunks.

        Use this tool before answering questions about uploaded
        documents, reports, spreadsheets, PDFs, or any knowledge
        base content. Returns relevant text snippets with document
        names and relevance scores.

        Args:
            query: Semantic search query (keywords or natural language).
            max_results: Maximum results to return (1–20).
            min_score: Minimum relevance score (0.0–1.0).

        Returns:
            `ToolResponse` with formatted search results.
        """
        if self._vector_store is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Knowledge base is not initialised.",
                    ),
                ],
            )

        try:
            results = await self.search(
                query=query,
                top_k=max_results,
            )

            # Filter by score
            filtered = [r for r in results if r.score >= min_score]

            if not filtered:
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text="No relevant documents found in the knowledge base.",
                        ),
                    ],
                )

            # Format output
            lines: list[str] = []
            for r in filtered:
                source = r.filename or r.document_id
                lines.append(
                    f"**[{source}]** (score: {r.score:.2f})",
                )
                if r.page_number is not None:
                    lines.append(f"  Page: {r.page_number}")
                lines.append(f"  {r.text}")
                lines.append("  ---")

            return ToolResponse(
                content=[TextBlock(type="text", text="\n".join(lines))],
            )

        except Exception as exc:
            logger.exception("knowledge_base_search failed: %s", exc)
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Knowledge base search error: {exc}",
                    ),
                ],
            )

    # ------------------------------------------------------------------
    # Auto-retrieval (context hook integration)
    # ------------------------------------------------------------------

    async def auto_knowledge_search(
        self,
        messages: list,
        agent_name: str = "",
    ) -> dict | None:
        """Auto-search KB before replies (called from context hook).

        Pattern matches :meth:`ReMeLightMemoryManager.auto_memory_search`.

        Returns ``None`` if auto-search is disabled or no results
        found, or a ``dict`` with ``msg`` key containing the
        augmented message list.
        """
        cfg = self._get_kb_config()
        if not cfg.get("auto_search_enabled", True):
            return None

        # Build query from recent messages
        query_parts: list[str] = []
        total = 0
        for msg in reversed(messages):
            remaining = 100 - total
            if remaining <= 0:
                break
            text = (msg.get_text_content() or "").strip()
            if not text:
                continue
            chunk = text[:remaining]
            query_parts.insert(0, chunk)
            total += len(chunk)

        query = " ".join(query_parts).strip()
        if not query:
            return None

        results = await self.search(
            query=query,
            top_k=cfg.get("max_results", 5),
        )
        min_score = cfg.get("min_score", 0.3)
        filtered = [r for r in results if r.score >= min_score]
        if not filtered:
            return None

        # Build tool result messages (same pattern as memory retrieve)
        from agentscope.message import Msg, ToolResultBlock, ToolUseBlock

        _id = uuid.uuid4().hex
        tool_use_input = {
            "query": query,
            "max_results": len(filtered),
        }

        lines = []
        for r in filtered:
            lines.append(f"[{r.filename or r.document_id}] ({r.score:.2f})")
            lines.append(r.text)
            lines.append("---")
        tool_text = "\n".join(lines)

        assistant_msg = Msg(
            name=agent_name,
            role="assistant",
            content=[
                TextBlock(
                    type="text",
                    text="Searching knowledge base for relevant context...",
                ),
                ToolUseBlock(
                    type="tool_use",
                    id=_id,
                    name="knowledge_base_search",
                    input=tool_use_input,
                    raw_input=json.dumps(tool_use_input, ensure_ascii=False),
                ),
            ],
        )
        tool_result_msg = Msg(
            name=agent_name,
            role="system",
            content=[
                ToolResultBlock(
                    type="tool_result",
                    id=_id,
                    name="knowledge_base_search",
                    output=[TextBlock(type="text", text=tool_text)],
                ),
            ],
        )

        msgs = list(messages) if isinstance(messages, list) else [messages]
        return {"msg": msgs + [assistant_msg, tool_result_msg]}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """Create required subdirectories."""
        self.kb_root.mkdir(parents=True, exist_ok=True)
        self._files_dir.mkdir(parents=True, exist_ok=True)
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> None:
        """Load document registry from JSON."""
        if self._registry_path.exists():
            try:
                data = json.loads(
                    self._registry_path.read_text(encoding="utf-8"),
                )
                self._document_registry = {
                    k: KnowledgeDocument(**v)
                    for k, v in data.get("documents", {}).items()
                }
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning(
                    "Corrupt KB registry, starting fresh: %s", exc,
                )
                self._document_registry = {}

    def _save_registry(self) -> None:
        """Persist document registry to JSON."""
        import asyncio

        data = {
            "documents": {
                k: v.model_dump()
                for k, v in self._document_registry.items()
            },
        }
        self.kb_root.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _get_embedding_config(self) -> dict[str, Any]:
        """Resolve embedding config (pattern from ReMeLightMemoryManager)."""
        try:
            from ...config.config import load_agent_config

            agent_config = load_agent_config(self.agent_id)
            reme_cfg = agent_config.running.reme_light_memory_config
            emb = reme_cfg.embedding_model_config
            from ...constant import EnvVarLoader

            return {
                "backend": emb.backend,
                "api_key": emb.api_key
                or EnvVarLoader.get_str("EMBEDDING_API_KEY", ""),
                "base_url": emb.base_url
                or EnvVarLoader.get_str("EMBEDDING_BASE_URL", ""),
                "model_name": emb.model_name
                or EnvVarLoader.get_str("EMBEDDING_MODEL_NAME", ""),
                "dimensions": emb.dimensions,
                "enable_cache": emb.enable_cache,
                "max_input_length": emb.max_input_length,
                "max_batch_size": emb.max_batch_size,
            }
        except Exception:
            return {
                "backend": "openai",
                "api_key": "",
                "base_url": "",
                "model_name": "",
                "dimensions": 1024,
            }

    def _get_kb_config(self) -> dict[str, Any]:
        """Resolve knowledge base config from agent config."""
        try:
            from ...config.config import load_agent_config

            agent_config = load_agent_config(self.agent_id)
            kb_cfg = agent_config.running.knowledge_base_config
            return {
                "enabled": kb_cfg.enabled,
                "chunk_size": kb_cfg.chunk_size,
                "chunk_overlap": kb_cfg.chunk_overlap,
                "max_results": kb_cfg.max_results,
                "min_score": kb_cfg.min_score,
                "auto_search_enabled": kb_cfg.auto_search_enabled,
                "supported_extensions": kb_cfg.supported_extensions,
                "file_watcher_enabled": kb_cfg.file_watcher_enabled,
            }
        except Exception:
            return {
                "enabled": True,
                "chunk_size": 500,
                "chunk_overlap": 50,
                "max_results": 5,
                "min_score": 0.1,
                "auto_search_enabled": True,
                "supported_extensions": list(SUPPORTED_EXTENSIONS),
                "file_watcher_enabled": True,
            }

    @staticmethod
    def _detect_store_backend() -> str:
        """Detect vector store backend (Windows → local, else auto)."""
        from ...constant import EnvVarLoader

        backend_env = EnvVarLoader.get_str("KB_STORE_BACKEND", "auto")
        if backend_env != "auto":
            return backend_env

        if platform.system() == "Windows":
            return "local"

        try:
            import chromadb  # noqa: F401
            return "chroma"
        except ImportError:
            return "local"

    async def _init_embedder(self) -> None:
        """Initialise the embedding function."""
        cfg = self._embedding_config

        if not cfg.get("base_url") or not cfg.get("model_name"):
            logger.warning(
                "Embedding not configured (missing base_url or model_name). "
                "Set EMBEDDING_BASE_URL and EMBEDDING_MODEL_NAME env vars, "
                "or configure ReMeLightMemoryConfig in agent.json. "
                "Knowledge base will use keyword-only search.",
            )
            self._embedding_fn = None
            return

        # We use a simple HTTP-based embedder via httpx (same pattern
        # as the OpenAI-compatible embedding endpoint).
        self._embedding_fn = _HttpEmbedder(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            model_name=cfg["model_name"],
            dimensions=cfg.get("dimensions", 1024),
            max_batch_size=cfg.get("max_batch_size", 10),
        )

    async def _embed_text(self, text: str) -> list[float]:
        """Embed a single query text."""
        embeddings = await self._embed_texts([text])
        return embeddings[0] if embeddings else [0.0] * 1024

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        if self._embedding_fn is None:
            # Fallback: zero embedding (keyword-only search degrades
            # gracefully on local store but not on Chroma).
            dims = self._embedding_config.get("dimensions", 1024)
            return [[0.0] * dims for _ in texts]

        return await self._embedding_fn.embed(texts)

    # ------------------------------------------------------------------
    # CJK tokenization (reused from ReMeLightMemoryManager)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_cjk(char: str) -> bool:
        """Check if a character is CJK."""
        cp = ord(char)
        return (
            (0x4E00 <= cp <= 0x9FFF)
            or (0x3400 <= cp <= 0x4DBF)
            or (0xF900 <= cp <= 0xFAFF)
        )

    @staticmethod
    def _tokenize_query(query: str, max_tokens: int = 50) -> list[str]:
        """Tokenize query for better search matching."""
        tokens: list[str] = []
        for word in query.split():
            if not word:
                continue
            if not any(
                KnowledgeBaseManager._is_cjk(c) for c in word
            ):
                tokens.append(word)
                if len(tokens) >= max_tokens:
                    break
                continue

            non_cjk_buffer: list[str] = []
            for char in word:
                if KnowledgeBaseManager._is_cjk(char):
                    if non_cjk_buffer:
                        tokens.append("".join(non_cjk_buffer))
                        non_cjk_buffer = []
                    tokens.append(char)
                else:
                    non_cjk_buffer.append(char)
                if len(tokens) >= max_tokens:
                    break
            if non_cjk_buffer and len(tokens) < max_tokens:
                tokens.append("".join(non_cjk_buffer))
            if len(tokens) >= max_tokens:
                break
        return tokens[:max_tokens]

    @staticmethod
    def _guess_mime(file_path: Path) -> str:
        """Guess MIME type from extension."""
        ext_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".tsv": "text/tab-separated-values",
            ".log": "text/plain",
        }
        return ext_map.get(file_path.suffix.lower(), "application/octet-stream")


# ---------------------------------------------------------------------------
# HTTP-based embedding client
# ---------------------------------------------------------------------------


class _HttpEmbedder:
    """Minimal OpenAI-compatible embedding HTTP client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        dimensions: int = 1024,
        max_batch_size: int = 10,
    ) -> None:
        import httpx

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._dimensions = dimensions
        self._max_batch_size = max_batch_size
        self._client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed *texts* via the embedding API."""
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._max_batch_size):
            batch = texts[i : i + self._max_batch_size]
            payload = {
                "model": self._model_name,
                "input": batch,
            }
            if self._dimensions:
                payload["dimensions"] = self._dimensions

            resp = await self._client.post(
                f"{self._base_url}/embeddings",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            all_embeddings.extend(
                item["embedding"] for item in data["data"]
            )
        return all_embeddings

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
