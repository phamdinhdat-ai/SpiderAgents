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
    DocumentScope,
    DocumentStatus,
    IndexingStatus,
    KnowledgeBaseInfo,
    KnowledgeDocument,
    SearchResult,
)
from .storage_backend import (
    LocalStorageBackend,
    StorageBackend,
    create_storage_backend,
)
from .vector_store import (
    ChromaVectorStore,
    LocalVectorStore,
    MilvusVectorStore,
    QdrantVectorStore,
    VectorStore,
)

logger = logging.getLogger(__name__)

# Prompt injected into the agent's system prompt (pattern:
# BaseMemoryManager.get_memory_prompt).
KB_GUIDANCE_PROMPT_EN = """\
## Knowledge Base

You have access to a knowledge base containing uploaded documents
(PDFs, spreadsheets, Word documents, markdown files, and more).

### When to Use `knowledge_list_documents`

- The user asks what documents they have uploaded ("list my files",
  "show my documents", "what's in my knowledge base?", etc.).
- The user wants a summary or inventory of their knowledge base.
- **Always call this FIRST** when the user asks about their
  documents in general — it gives you the full picture before
  you search specific content.

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

- `knowledge_list_documents()` — lists all accessible documents
  with status, size, chunk count, and upload date.  Use this to
  answer inventory questions.
- `knowledge_base_search(query="...")` — semantic search with a
  specific, keyword-rich query. Returns relevant text chunks with
  source filenames and relevance scores.
"""

KB_GUIDANCE_PROMPT_VI = """\
## Kho Kiến Thức

Bạn có quyền truy cập vào kho kiến thức chứa các tài liệu đã tải lên
(PDF, bảng tính, tài liệu Word, tệp markdown, v.v.).

### Khi nào sử dụng `knowledge_list_documents`

- Người dùng hỏi họ có những tài liệu nào ("liệt kê tài liệu của tôi",
  "cho tôi xem các files", "có gì trong kho kiến thức?", v.v.).
- Người dùng muốn tổng quan về kho kiến thức của họ.
- **Luôn gọi công cụ này TRƯỚC** khi người dùng hỏi chung chung về
  tài liệu — nó cung cấp bức tranh toàn cảnh trước khi bạn tìm
  kiếm nội dung cụ thể.

### Khi nào sử dụng `knowledge_base_search`

- Người dùng hỏi về nội dung từ các tài liệu hoặc tệp đã tải lên.
- Người dùng tham chiếu đến một tài liệu theo tên.
- Người dùng đặt câu hỏi thực tế mà câu trả lời có thể có trong
  kho kiến thức — **kiểm tra KB trước**, sau đó mới dùng dữ liệu
  huấn luyện nếu không tìm thấy.
- Người dùng yêu cầu so sánh chéo tài liệu hoặc phân tích đa tài liệu.
- Người dùng nói "tìm kiếm tài liệu của tôi", "tìm trong tệp", v.v.

### Cách sử dụng

- `knowledge_list_documents()` — liệt kê tất cả tài liệu có thể truy
  cập kèm trạng thái, kích thước, số lượng đoạn và ngày tải lên.
  Dùng để trả lời câu hỏi về tổng quan tài liệu.
- `knowledge_base_search(query="...")` — tìm kiếm ngữ nghĩa với truy
  vấn cụ thể, giàu từ khóa. Trả về các đoạn văn bản liên quan nhất
  kèm tên tệp nguồn và điểm liên quan.
"""

from ..constant import KNOWLEDGE_MAX_FILE_SIZE_BYTES

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".xlsx", ".xlsm", ".md", ".markdown",
    ".txt", ".log", ".csv", ".tsv",
})
# (MAX_FILE_SIZE_BYTES migrated to constant.py as KNOWLEDGE_MAX_FILE_SIZE_BYTES)
MAX_PAGES = 500
KB_STORE_VERSION = "v1"


def _format_file_size(bytes_val: int) -> str:
    """Format a byte count as a human-readable string."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    return f"{bytes_val / (1024 * 1024):.1f} MB"


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
        self._storage_backend: StorageBackend | None = None
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

        # Migrate legacy documents (owner=None) — assign ownership to
        # "admin" so they are no longer visible to all authenticated users.
        self._migrate_legacy_ownership()

        # Migrate flat files → user-scoped subdirectories (Phase 1).
        self._migrate_file_storage_v2()

        # Resolve embedding config (reuse pattern from ReMeLightMemoryManager)
        self._embedding_config = self._get_embedding_config()

        # Create chunker from agent config
        chunk_cfg = self._get_kb_config()
        self._chunker = TextChunker(
            chunk_size=chunk_cfg.get("chunk_size", 500),
            chunk_overlap=chunk_cfg.get("chunk_overlap", 50),
        )

        # Choose storage backend (local / MinIO) from config
        storage_cfg = self._get_storage_config()
        self._storage_backend = create_storage_backend(
            config=storage_cfg.get("file_storage", {}),
            root_dir=str(self._files_dir),
        )
        await self._storage_backend.start()

        # Choose vector store backend (local / Chroma / Qdrant / Milvus)
        backend = self._detect_store_backend()
        # Use user-scoped collection so documents persist across agent switches.
        # When no user context is available, fall back to agent-scoped.
        username = self._resolve_kb_username()
        collection = f"kb_{username}"
        store_path = str(self._store_dir)

        if backend == "chroma":
            self._vector_store = ChromaVectorStore(collection, store_path)
        elif backend == "qdrant":
            vs_cfg = storage_cfg.get("vector_store", {})
            self._vector_store = QdrantVectorStore(
                collection_name=collection,
                url=vs_cfg.get("qdrant_url", ""),
                api_key=vs_cfg.get("qdrant_api_key", ""),
            )
        elif backend == "milvus":
            vs_cfg = storage_cfg.get("vector_store", {})
            self._vector_store = MilvusVectorStore(
                collection_name=collection,
                uri=vs_cfg.get("milvus_uri", ""),
                token=vs_cfg.get("milvus_token", ""),
                host=vs_cfg.get("milvus_host", "localhost"),
                port=vs_cfg.get("milvus_port", 19530),
            )
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
        if self._storage_backend is not None:
            await self._storage_backend.close()
            self._storage_backend = None
        self._started = False
        logger.info("KnowledgeBaseManager closed: agent=%s", self.agent_id)

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        file_path: Path,
        kb_name: str = "default",
        owner: str | None = None,
        original_name: str | None = None,
    ) -> KnowledgeDocument:
        """Parse, chunk, embed, and store a document.

        Args:
            file_path: Path to the source file (will be copied into KB
                storage).
            kb_name: Named knowledge base (default ``"default"``).
            owner: Username of the uploading user (``None`` = legacy).
            original_name: Original filename from the upload (used for
                storage naming).  When *None*, ``file_path.name`` is used.

        Returns:
            :class:`KnowledgeDocument` with the indexing result.
        """
        if not file_path.is_file():
            raise FileNotFoundError(f"Document not found: {file_path}")

        # Use the original upload name when available; otherwise fall
        # back to the temp-file name.
        display_name = original_name or file_path.name

        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )

        file_size = file_path.stat().st_size
        if file_size > KNOWLEDGE_MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File too large: {file_size} bytes "
                f"(max {KNOWLEDGE_MAX_FILE_SIZE_BYTES})",
            )

        # --- Deduplication: same content hash + same filename → skip ---
        content_hash = self._hash_file(file_path)
        duplicate = self._find_duplicate(owner, display_name, content_hash)
        if duplicate is not None:
            logger.info(
                "Dedup: skipping %s (already indexed as %s, hash=%s)",
                display_name, duplicate.id, content_hash[:16],
            )
            return duplicate

        # Create document record — store under user-scoped subdirectory
        # so the original filename is preserved and easy to cite.
        doc_id = uuid.uuid4().hex
        stored_path = self._resolve_stored_path(
            display_name,
            owner=owner,
        )

        doc = KnowledgeDocument(
            id=doc_id,
            filename=display_name,
            file_path=str(stored_path),
            kb_name=kb_name,
            mime_type=self._guess_mime(file_path),
            size=file_size,
            status=DocumentStatus.INDEXING,
            owner=owner,
        )
        self._document_registry[doc_id] = doc
        self._save_registry()

        # Persist file via storage backend (local or MinIO)
        if self._storage_backend is not None:
            stored_path_str = await self._storage_backend.store(
                file_path,
                owner or "_unowned",
                stored_path.name,
            )
            doc.file_path = stored_path_str

        try:
            # Parse → chunk → embed → store
            if self._chunker is None:
                raise RuntimeError("Chunker not initialized")

            # Chunk from the original file (always local; stored copy is
            # for retrieval)
            chunks = self._chunker.chunk_document(file_path, doc_id)
            if not chunks:
                raise ValueError("Document produced no text content")

            # Propagate ACL metadata to every chunk
            for chunk in chunks:
                chunk.metadata["owner"] = owner or ""
                chunk.metadata["scope"] = "private"
                chunk.metadata["shared_with"] = ""

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
        doc.metadata["content_hash"] = content_hash
        self._save_registry()
        return doc

    async def remove_document(
        self,
        document_id: str,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> bool:
        """Delete a document and its vector chunks.

        Only the owner or an admin may remove a document.

        Returns ``True`` if the document was found, authorised, and removed.
        """
        doc = self._document_registry.get(document_id)
        if doc is None:
            return False

        # Ownership check: admin or owner
        if user_role != "admin" and user_id is not None and doc.owner != user_id:
            return False

        self._document_registry.pop(document_id, None)

        # Remove from vector store
        if self._vector_store is not None:
            await self._vector_store.delete(document_id)

        # Remove stored file (via storage backend when available)
        if self._storage_backend is not None:
            try:
                await self._storage_backend.delete(doc.file_path)
            except Exception:
                pass
        else:
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
        user_id: str | None = None,
        user_role: str | None = None,
        scope_filter: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List documents, optionally filtered by KB, ACL, and scope.

        Args:
            kb_name: Filter by knowledge base name.
            user_id: Authenticated username (from auth token).
            user_role: ``"admin"``, ``"user"``, or ``None``.
            scope_filter: ``"my"`` (owned by user), ``"shared"``
                (non-private docs user can see), or ``None`` (all
                accessible).

        Returns:
            Documents accessible by *user_id*, sorted by date descending.
        """
        docs = list(self._document_registry.values())

        # KB filter
        if kb_name is not None:
            docs = [d for d in docs if d.kb_name == kb_name]

        # Scope filter (before ACL filter)
        if scope_filter == "my" and user_id is not None:
            docs = [d for d in docs if d.owner == user_id]
        elif scope_filter == "shared" and user_id is not None:
            docs = [
                d for d in docs
                if d.owner != user_id and (
                    d.scope == DocumentScope.PUBLIC
                    or (d.scope == DocumentScope.SHARED and user_id in d.shared_with)
                )
            ]

        # ACL filter — only for non-admin users
        docs = self._filter_docs_by_access(docs, user_id, user_role)

        docs.sort(key=lambda d: d.created_at, reverse=True)
        return docs

    async def get_document(
        self,
        document_id: str,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> KnowledgeDocument | None:
        """Get a single document by ID, respecting ACL.

        Returns ``None`` when the document does not exist OR the
        requesting user lacks access (callers should raise 404).
        """
        doc = self._document_registry.get(document_id)
        if doc is None:
            return None
        if not self._check_document_access(doc, user_id, user_role):
            return None
        return doc

    async def get_indexing_status(
        self,
        kb_name: str = "default",
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> IndexingStatus:
        """Return aggregate indexing status for a knowledge base."""
        docs = await self.list_documents(
            kb_name=kb_name,
            user_id=user_id,
            user_role=user_role,
        )
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

    async def list_knowledge_bases(
        self,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """List all named knowledge bases with summary stats.

        Args:
            user_id: Authenticated username (from auth token).
                Only KBs accessible to this user are returned.
            user_role: ``"admin"``, ``"user"``, or ``None``.

        Returns:
            One :class:`KnowledgeBaseInfo` per named KB the user can access.
        """
        groups: dict[str, list[KnowledgeDocument]] = {}
        for doc in self._document_registry.values():
            # ACL: only count documents the user can access
            if not self._check_document_access(doc, user_id, user_role):
                continue
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

    async def reindex_all(
        self,
        kb_name: str = "default",
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> dict[str, Any]:
        """Clear and re-index all accessible documents in *kb_name*.

        Non-admin users can only re-index their own documents.

        Returns a summary dict with counts.
        """
        docs = await self.list_documents(
            kb_name=kb_name,
            user_id=user_id,
            user_role=user_role,
        )
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
                    await self.ingest_document(
                        stored,
                        kb_name=kb_name,
                        owner=doc.owner,
                    )
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

    async def share_document(
        self,
        document_id: str,
        shared_with: list[str],
        scope: DocumentScope,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> KnowledgeDocument | None:
        """Update a document's sharing settings.

        Only the owner or an admin may share a document.

        Args:
            document_id: Target document ID.
            shared_with: List of usernames to grant access to.
            scope: Target scope (``SHARED`` or ``PUBLIC``).
            user_id: Requesting user (must be owner or admin).
            user_role: Requesting user's role.

        Returns:
            Updated :class:`KnowledgeDocument`, or ``None`` if the
            document was not found or the user lacks permission.
        """
        doc = self._document_registry.get(document_id)
        if doc is None:
            return None

        # Only owner or admin can share
        if user_role != "admin" and user_id is not None and doc.owner != user_id:
            return None

        doc.scope = scope
        doc.shared_with = shared_with
        self._save_registry()
        return doc

    # ------------------------------------------------------------------
    # Search (synchronous tool interface)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 5,
        kb_names: list[str] | None = None,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> list[SearchResult]:
        """Semantic search across accessible documents."""
        if self._vector_store is None:
            return []

        # Tokenize query (CJK-aware, same logic as ReMeLightMemoryManager)
        query_tokens = " ".join(self._tokenize_query(query))

        # Get query embedding
        embedding = await self._embed_text(query_tokens)

        # Vector search — fetch more than needed to compensate for ACL
        # post-filtering, which may discard results the caller cannot see.
        fetch_count = max(top_k * 3, top_k + 20)
        results = await self._vector_store.search(
            embedding,
            top_k=fetch_count,
            filter_kb_names=kb_names,
        )

        # Post-filter by ACL using the document registry
        filtered: list[SearchResult] = []
        for r in results:
            doc = self._document_registry.get(r.document_id)
            if doc is not None:
                if not self._check_document_access(doc, user_id, user_role):
                    continue
                r.filename = doc.filename
                r.kb_name = doc.kb_name
                filtered.append(r)

        return filtered[:top_k]

    # ------------------------------------------------------------------
    # Agent tool integration
    # ------------------------------------------------------------------

    def list_kb_tools(self) -> list:
        """Return tool functions to register with the agent toolkit.

        Pattern matches :meth:`BaseMemoryManager.list_memory_tools`.
        """
        return [self.knowledge_base_search, self.knowledge_list_documents]

    def get_kb_prompt(self, language: str = "en") -> str:
        """Return KB guidance for injection into the system prompt.

        Pattern matches :meth:`BaseMemoryManager.get_memory_prompt`.
        """
        prompts = {
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
            from ..app.agent_context import (
                get_current_auth_user_id,
                get_current_auth_user_role,
            )

            results = await self.search(
                query=query,
                top_k=max_results,
                user_id=get_current_auth_user_id(),
                user_role=get_current_auth_user_role(),
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

            # Format output with citation markers
            content_blocks: list[TextBlock] = []
            citations: list[dict] = []
            for r in filtered:
                source = r.filename or r.document_id
                page_info = f", p. {r.page_number}" if r.page_number else ""
                citation_marker = (
                    f"[📄 **{source}**{page_info} — score: {r.score:.2f}]"
                )
                block_text = f"{citation_marker}\n{r.text}"
                content_blocks.append(TextBlock(type="text", text=block_text))
                citations.append({
                    "document_id": r.document_id,
                    "filename": r.filename,
                    "chunk_id": r.chunk_id,
                    "page_number": r.page_number,
                    "score": round(r.score, 4),
                })

            return ToolResponse(
                content=content_blocks,
                metadata={
                    "citations": citations,
                    "tool": "knowledge_base_search",
                    "total_results": len(citations),
                },
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

    async def knowledge_list_documents(
        self,
        kb_name: str = "",
        status_filter: str = "",
    ) -> ToolResponse:
        """List all documents in the user's knowledge base.

        Use this tool when the user asks what documents they have
        uploaded, wants to see their file inventory, or needs a
        summary of their knowledge base contents.  Returns filename,
        status, size, chunk count, and upload date for each document.

        Args:
            kb_name: Optional knowledge base name to filter by.
                     Leave empty to list documents from all KBs the
                     user can access.
            status_filter: Optional status filter — ``"ready"``,
                           ``"indexing"``, ``"error"``, or empty for all.

        Returns:
            `ToolResponse` with formatted document listing.
        """
        try:
            from ..app.agent_context import (
                get_current_auth_user_id,
                get_current_auth_user_role,
            )

            user_id = get_current_auth_user_id()
            user_role = get_current_auth_user_role()

            docs = await self.list_documents(
                kb_name=kb_name if kb_name else None,
                user_id=user_id,
                user_role=user_role,
            )

            # Apply status filter
            if status_filter:
                docs = [
                    d for d in docs
                    if d.status.value == status_filter
                ]

            if not docs:
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                "📭 You have no documents in your knowledge base yet. "
                                "Upload files (PDF, DOCX, XLSX, Markdown, TXT, CSV) "
                                "through the Knowledge Base page in the web console."
                            ),
                        ),
                    ],
                )

            # Build a formatted listing
            lines: list[str] = [
                f"📚 **Your Knowledge Base** — {len(docs)} document(s)\n",
            ]
            lines.append(
                "| # | Filename | Status | Size | Chunks | Uploaded | KB |",
            )
            lines.append(
                "|---|----------|--------|------|--------|----------|----|",
            )

            for i, doc in enumerate(docs, 1):
                status_emoji = {
                    "ready": "✅",
                    "indexing": "🔄",
                    "pending": "⏳",
                    "error": "❌",
                }.get(doc.status.value, "❓")

                size_str = _format_file_size(doc.size)
                date_str = doc.created_at[:10] if doc.created_at else "N/A"
                lines.append(
                    f"| {i} | {doc.filename} | {status_emoji} {doc.status.value}"
                    f" | {size_str} | {doc.chunk_count} | {date_str}"
                    f" | {doc.kb_name} |",
                )

            # Add summary counts by status
            ready = sum(1 for d in docs if d.status.value == "ready")
            indexing = sum(1 for d in docs if d.status.value == "indexing")
            error = sum(1 for d in docs if d.status.value == "error")
            lines.append(
                f"\n📊 **Summary**: {ready} ready, {indexing} indexing, "
                f"{error} error(s)",
            )

            # Add per-KB breakdown when listing across KBs
            if not kb_name:
                kb_groups: dict[str, int] = {}
                for d in docs:
                    kb_groups[d.kb_name] = kb_groups.get(d.kb_name, 0) + 1
                if len(kb_groups) > 1:
                    lines.append("📂 **By knowledge base**:")
                    for name, count in sorted(kb_groups.items()):
                        lines.append(f"  • {name}: {count} document(s)")

            return ToolResponse(
                content=[TextBlock(type="text", text="\n".join(lines))],
                metadata={
                    "tool": "knowledge_list_documents",
                    "total_documents": len(docs),
                    "ready_count": ready,
                    "indexing_count": indexing,
                    "error_count": error,
                },
            )

        except Exception as exc:
            logger.exception("knowledge_list_documents failed: %s", exc)
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Knowledge base listing error: {exc}",
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

        from ..app.agent_context import (
            get_current_auth_user_id,
            get_current_auth_user_role,
        )

        results = await self.search(
            query=query,
            top_k=cfg.get("max_results", 5),
            user_id=get_current_auth_user_id(),
            user_role=get_current_auth_user_role(),
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

    def _check_document_access(
        self,
        doc: KnowledgeDocument,
        user_id: str | None,
        user_role: str | None,
    ) -> bool:
        """Check whether *user_id* can access *doc*.

        Rules (first match wins):
        1. Admin — always allowed.
        2. No user context (auth disabled) — allow all (single-user mode).
        3. Legacy doc (owner is None) — admin only (falls through to rule 6
           for non-admin users; admins are caught by rule 1).
        4. Owner match — allowed.
        5. scope == PUBLIC — allowed for all authenticated users.
        6. scope == SHARED and user_id in shared_with — allowed.
        7. Otherwise — denied.
        """
        # Admin override
        if user_role == "admin":
            return True

        # No user context (auth disabled / skipped) — single-user mode,
        # allow all.  Multi-user isolation requires auth to be enforced
        # (remove 127.0.0.1 from allow_no_auth_hosts in settings).
        if user_id is None:
            return True

        # Owner
        if doc.owner == user_id:
            return True

        # Public
        if doc.scope == DocumentScope.PUBLIC:
            return True

        # Shared
        if doc.scope == DocumentScope.SHARED and user_id in doc.shared_with:
            return True

        return False

    def _filter_docs_by_access(
        self,
        docs: list[KnowledgeDocument],
        user_id: str | None,
        user_role: str | None,
    ) -> list[KnowledgeDocument]:
        """Filter a list of documents to those accessible by *user_id*.

        Admin users and unauthenticated callers (single-user mode) see
        all documents.  Authenticated non-admin users only see documents
        they are authorised for.
        """
        if user_role == "admin" or user_id is None:
            return list(docs)
        return [
            d for d in docs
            if self._check_document_access(d, user_id, user_role)
        ]

    def _migrate_legacy_ownership(self) -> None:
        """Assign ownership of legacy documents (``owner=None``) to the
        ``"admin"`` user so they are no longer visible to all authenticated
        users.  Writes the registry only when changes are made.

        Idempotent — a sentinel file (``.kb_ownership_v2``) prevents
        re-execution.
        """
        sentinel = self.kb_root / ".kb_ownership_v2"
        if sentinel.exists():
            return

        migrated = 0
        for doc in self._document_registry.values():
            if doc.owner is None:
                # Try to infer owner from kb_name (users get kb_name ==
                # username via _resolve_kb_name).  If kb_name looks like
                # a username, assign to that user; otherwise fall back to
                # "admin".
                inferred = doc.kb_name if doc.kb_name not in ("default", "") else None
                doc.owner = inferred or "admin"
                migrated += 1

        if migrated:
            self._save_registry()
            logger.info(
                "Migrated %d legacy documents to explicit ownership",
                migrated,
            )

        sentinel.touch()

    # ------------------------------------------------------------------
    # File path helpers
    # ------------------------------------------------------------------

    def _resolve_stored_path(
        self,
        filename: str,
        *,
        owner: str | None = None,
    ) -> Path:
        """Resolve a storage path for *filename* under a user-scoped
        subdirectory, handling name collisions with a counter suffix.

        Directory layout::

            {kb_root}/files/{owner}/{filename}
            {kb_root}/files/_unowned/{filename}
        """
        safe_name = Path(filename).name  # strip path separators
        user_dir = self._files_dir / (owner or "_unowned")
        user_dir.mkdir(parents=True, exist_ok=True)

        target = user_dir / safe_name
        if not target.exists():
            return target

        # Collision — append counter
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while target.exists():
            target = user_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return target

    def _migrate_file_storage_v2(self) -> None:
        """One-time migration: move files from the old flat ``files/``
        directory into user-scoped subdirectories.

        Idempotent — a sentinel file ``.kb_files_v2`` prevents
        re-execution.
        """
        sentinel = self.kb_root / ".kb_files_v2"
        if sentinel.exists():
            return

        moved = 0
        for doc in self._document_registry.values():
            old_path = Path(doc.file_path)
            if not old_path.exists():
                # Source already missing — just update the registry path
                new_path = self._resolve_stored_path(
                    doc.filename,
                    owner=doc.owner,
                )
                doc.file_path = str(new_path)
                continue

            # Only move files that are directly under the old flat dir
            if old_path.parent != self._files_dir:
                continue

            new_path = self._resolve_stored_path(
                doc.filename,
                owner=doc.owner,
            )
            try:
                old_path.rename(new_path)
                doc.file_path = str(new_path)
                moved += 1
            except OSError:
                logger.warning(
                    "Failed to migrate KB file %s → %s",
                    old_path, new_path,
                )

        if moved:
            self._save_registry()
            logger.info(
                "Migrated %d KB files to user-scoped directories",
                moved,
            )

        sentinel.touch()

    def _resolve_kb_username(self) -> str:
        """Resolve the username for knowledge base namespace.

        Returns the authenticated user ID when available, otherwise
        falls back to the agent ID for backward compatibility.
        """
        try:
            from ..app.agent_context import get_current_auth_user_id

            user_id = get_current_auth_user_id()
            if user_id:
                return user_id
        except Exception:
            pass
        return self.agent_id

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
            from ..config.config import load_agent_config

            agent_config = load_agent_config(self.agent_id)
            reme_cfg = agent_config.running.reme_light_memory_config
            emb = reme_cfg.embedding_model_config
            from ..constant import EnvVarLoader

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
            from ..config.config import load_agent_config

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

    def _get_storage_config(self) -> dict[str, Any]:
        """Load storage backends configuration from settings.json.

        Resolution order:
        1. ``settings.json`` → ``storage_backends`` key
        2. Environment variables (per-backend)
        3. Defaults (local file store + auto vector store)
        """
        try:
            from ..constant import WORKING_DIR as _WD
            settings_path = _WD / "settings.json"
            if settings_path.is_file():
                data = json.loads(settings_path.read_text("utf-8"))
                sb = data.get("storage_backends") or data.get("storage")
                if sb:
                    return sb
        except Exception:
            pass
        return {}

    @staticmethod
    def _detect_store_backend() -> str:
        """Detect vector store backend.

        Resolution order:
        1. ``settings.json`` → ``storage_backends.vector_store.backend``
        2. ``KB_STORE_BACKEND`` environment variable
        3. Auto-detect: Windows → ``"local"``, otherwise → ``"chroma"``
        """
        # Check settings.json first
        try:
            from ..constant import WORKING_DIR as _WD
            settings_path = _WD / "settings.json"
            if settings_path.is_file():
                data = json.loads(settings_path.read_text("utf-8"))
                sb = data.get("storage_backends") or data.get("storage")
                if sb:
                    vs = sb.get("vector_store", {})
                    configured = vs.get("backend", "auto")
                    if configured and configured != "auto":
                        return configured
        except Exception:
            pass

        # Fall back to env var
        from ..constant import EnvVarLoader

        backend_env = EnvVarLoader.get_str("KB_STORE_BACKEND", "auto")
        if backend_env != "auto":
            return backend_env

        # Auto-detect
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
    def _hash_file(file_path: Path) -> str:
        """Compute SHA-256 hex digest of a file for deduplication."""
        import hashlib

        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _find_duplicate(
        self,
        owner: str | None,
        filename: str,
        content_hash: str,
    ) -> KnowledgeDocument | None:
        """Return an existing READY document with matching owner, filename,
        and content hash, or ``None``.
        """
        for doc in self._document_registry.values():
            if (
                doc.owner == owner
                and doc.filename == filename
                and doc.metadata.get("content_hash") == content_hash
                and doc.status == DocumentStatus.READY
            ):
                return doc
        return None

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
