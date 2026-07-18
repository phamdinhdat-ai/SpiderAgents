# -*- coding: utf-8 -*-
"""REST API router for knowledge base document management and search."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from ..agent_context import (
    get_agent_for_request,
    get_current_auth_user_id,
    get_current_auth_user_role,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Size limit for uploads: 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Search query body."""

    query: str = Field(..., min_length=1, description="Search query text")
    kb_names: Optional[list[str]] = Field(
        default=None,
        description="Knowledge bases to search (None = all)",
    )
    max_results: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.1, ge=0.0, le=1.0)


class ReindexRequest(BaseModel):
    """Re-index request body."""

    kb_name: str = Field(default="default", description="Knowledge base to re-index")


class ShareDocumentRequest(BaseModel):
    """Request body for sharing a knowledge document."""

    shared_with: list[str] = Field(
        default_factory=list,
        description="Usernames to grant explicit access to",
    )
    scope: str = Field(
        default="shared",
        description="Target access scope: 'shared' or 'public'",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_context() -> tuple[str | None, str | None]:
    """Extract authenticated user identity from ContextVar.

    Returns:
        ``(user_id, role)`` tuple.  Both values are ``None`` when
        auth is disabled or unauthenticated.
    """
    return get_current_auth_user_id(), get_current_auth_user_role()


def _resolve_kb_name(kb_name: str, user_id: str | None) -> str:
    """Resolve the knowledge base name for the current user.

    When *kb_name* is ``"default"`` and a user is authenticated,
    substitute the username so each user gets their own isolated
    knowledge base namespace.  Explicit non-default names are
    passed through unchanged (used for shared/public KBs).
    """
    if kb_name == "default" and user_id:
        return user_id
    return kb_name


def _get_kb_manager(workspace):
    """Get KnowledgeBaseManager from workspace."""
    kb = workspace.knowledge_base_manager
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base manager not initialized for this agent",
        )
    return kb


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/documents/upload", summary="Upload documents to knowledge base")
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(..., description="Document files to upload"),
    kb_name: str = Query(
        default="default",
        description="Target knowledge base name",
    ),
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Upload one or more documents for indexing.

    Supported formats: PDF, DOCX, XLSX, Markdown, TXT, CSV, TSV, LOG.
    Max file size: 50 MB per file.

    Documents are copied into the knowledge base storage, parsed,
    chunked, embedded, and indexed for semantic search.

    Query params:
    - **kb_name**: Target knowledge base (default ``"default"``).
    """
    import tempfile

    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, _role = _get_user_context()
    kb_name = _resolve_kb_name(kb_name, user_id)

    results = []
    errors = []

    for file in files:
        # Validate file size by reading
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            errors.append({
                "filename": file.filename,
                "error": f"File exceeds {MAX_UPLOAD_SIZE} bytes",
            })
            continue

        # Write to temp file then ingest
        suffix = ""
        if file.filename:
            suffix = "." + file.filename.rsplit(".", 1)[-1] if "." in file.filename else ""
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            from pathlib import Path
            doc = await kb.ingest_document(
                file_path=Path(tmp_path),
                kb_name=kb_name,
                owner=user_id,
            )
            results.append({
                "document_id": doc.id,
                "filename": doc.filename,
                "kb_name": doc.kb_name,
                "status": doc.status.value,
                "chunk_count": doc.chunk_count,
                "message": (
                    "Document indexed successfully"
                    if doc.status.value == "ready"
                    else f"Indexing failed: {doc.error_message}"
                ),
            })
        except Exception as exc:
            logger.exception("Upload failed for %s", file.filename)
            errors.append({
                "filename": file.filename,
                "error": str(exc),
            })
        finally:
            # Clean up temp file
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return {
        "results": results,
        "errors": errors,
        "total": len(results),
    }


@router.get("/documents", summary="List knowledge base documents")
async def list_documents(
    request: Request,
    kb_name: Optional[str] = Query(
        default=None,
        description="Filter by knowledge base name",
    ),
    scope: Optional[str] = Query(
        default=None,
        description="``my`` (owned), ``shared`` (non-private visible), or omit (all accessible)",
    ),
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """List indexed documents visible to the authenticated user.

    Query params:
    - **kb_name**: Filter by knowledge base name.
    - **scope**: ``"my"`` (owned by user), ``"shared"``
      (non-private docs user can see), or omit for all accessible.
    """
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()
    kb_name = _resolve_kb_name(kb_name or "default", user_id)

    docs = await kb.list_documents(
        kb_name=kb_name,
        user_id=user_id,
        user_role=role,
        scope_filter=scope,
    )
    return {
        "documents": [d.model_dump() for d in docs],
        "total": len(docs),
    }


@router.get("/list", summary="List knowledge bases")
async def list_knowledge_bases(
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """List all named knowledge bases with summary stats."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()

    kbs = await kb.list_knowledge_bases(user_id=user_id, user_role=role)
    return {
        "knowledge_bases": [k.model_dump() for k in kbs],
        "total": len(kbs),
    }


@router.get("/documents/{document_id}", summary="Get document details")
async def get_document(
    document_id: str,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Get a single document's metadata by ID (access-controlled)."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()

    doc = await kb.get_document(
        document_id,
        user_id=user_id,
        user_role=role,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return doc.model_dump()


@router.delete("/documents/{document_id}", summary="Delete a document")
async def delete_document(
    document_id: str,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Delete a document and all its vector chunks (owner or admin only)."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()

    removed = await kb.remove_document(
        document_id,
        user_id=user_id,
        user_role=role,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "deleted", "document_id": document_id}


@router.post("/search", summary="Search the knowledge base")
async def search_knowledge_base(
    body: SearchRequest,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Semantic search across documents accessible to the user."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()

    results = await kb.search(
        query=body.query,
        top_k=body.max_results,
        kb_names=body.kb_names,
        user_id=user_id,
        user_role=role,
    )

    # Filter by min_score
    filtered = [r for r in results if r.score >= body.min_score]

    return {
        "results": [r.model_dump() for r in filtered],
        "total": len(filtered),
        "query": body.query,
    }


@router.get("/status", summary="Get indexing status")
async def get_status(
    request: Request,
    kb_name: str = Query(
        default="default",
        description="Knowledge base name",
    ),
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Get aggregate indexing progress and stats for accessible documents."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()
    kb_name = _resolve_kb_name(kb_name, user_id)

    status = await kb.get_indexing_status(
        kb_name=kb_name,
        user_id=user_id,
        user_role=role,
    )
    return status.model_dump()


@router.post("/reindex", summary="Re-index all documents")
async def reindex_all(
    body: ReindexRequest = ReindexRequest(),
    request: Request = None,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Clear and re-index accessible documents in a knowledge base.

    Non-admin users can only re-index their own documents.
    """
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()
    kb_name = _resolve_kb_name(body.kb_name if body else "default", user_id)

    result = await kb.reindex_all(
        kb_name=kb_name,
        user_id=user_id,
        user_role=role,
    )
    return result


@router.post("/documents/{document_id}/share", summary="Share a document")
async def share_document(
    document_id: str,
    body: ShareDocumentRequest,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Update a document's sharing settings (owner or admin only).

    Request body:
    - **shared_with**: List of usernames to grant access to.
    - **scope**: ``"shared"`` or ``"public"``.
    """
    from ...knowledge.models import DocumentScope

    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)
    user_id, role = _get_user_context()

    # Validate scope
    if body.scope not in ("shared", "public"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scope '{body.scope}'. Must be 'shared' or 'public'.",
        )

    target_scope = (
        DocumentScope.SHARED if body.scope == "shared"
        else DocumentScope.PUBLIC
    )

    doc = await kb.share_document(
        document_id=document_id,
        shared_with=body.shared_with,
        scope=target_scope,
        user_id=user_id,
        user_role=role,
    )
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found or access denied",
        )

    return {
        "status": "shared",
        "document_id": document_id,
        "scope": body.scope,
        "shared_with": body.shared_with,
    }
