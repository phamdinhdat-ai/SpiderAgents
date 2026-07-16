# -*- coding: utf-8 -*-
"""REST API router for knowledge base document management and search."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from ..agent_context import get_agent_for_request

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    kb_name: str = "default",
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Upload one or more documents for indexing.

    Supported formats: PDF, DOCX, XLSX, Markdown, TXT, CSV, TSV, LOG.
    Max file size: 50 MB per file.

    Documents are copied into the knowledge base storage, parsed,
    chunked, embedded, and indexed for semantic search.
    """
    import tempfile

    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

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
    kb_name: Optional[str] = None,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """List all indexed documents with their status."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    docs = await kb.list_documents(kb_name=kb_name)
    return {
        "documents": [d.model_dump() for d in docs],
        "total": len(docs),
    }


@router.get("/documents/{document_id}", summary="Get document details")
async def get_document(
    document_id: str,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Get a single document's metadata by ID."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    doc = await kb.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return doc.model_dump()


@router.delete("/documents/{document_id}", summary="Delete a document")
async def delete_document(
    document_id: str,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Delete a document and all its vector chunks."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    removed = await kb.remove_document(document_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "deleted", "document_id": document_id}


@router.post("/search", summary="Search the knowledge base")
async def search_knowledge_base(
    body: SearchRequest,
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Semantic search across all indexed documents."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    results = await kb.search(
        query=body.query,
        top_k=body.max_results,
        kb_names=body.kb_names,
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
    kb_name: str = "default",
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Get aggregate indexing progress and stats."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    status = await kb.get_indexing_status(kb_name=kb_name)
    return status.model_dump()


@router.post("/reindex", summary="Re-index all documents")
async def reindex_all(
    body: ReindexRequest = ReindexRequest(),
    request: Request = None,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """Clear and re-index all documents in a knowledge base."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    result = await kb.reindex_all(kb_name=body.kb_name)
    return result


@router.get("/list", summary="List knowledge bases")
async def list_knowledge_bases(
    request: Request,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-Id"),
):
    """List all named knowledge bases with summary stats."""
    workspace = await get_agent_for_request(request)
    kb = _get_kb_manager(workspace)

    kbs = await kb.list_knowledge_bases()
    return {
        "knowledge_bases": [k.model_dump() for k in kbs],
        "total": len(kbs),
    }
