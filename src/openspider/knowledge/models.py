# -*- coding: utf-8 -*-
"""Pydantic data models for the knowledge base system."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Indexing status for a knowledge document."""

    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


class DocumentChunk(BaseModel):
    """A single text chunk extracted from a document."""

    chunk_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique chunk identifier",
    )
    document_id: str = Field(..., description="Parent document ID")
    text: str = Field(..., description="Chunk text content")
    chunk_index: int = Field(default=0, description="Position in document")
    page_number: Optional[int] = Field(
        default=None,
        description="Page number (PDF only)",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (section, heading, etc.)",
    )


class KnowledgeDocument(BaseModel):
    """Metadata about an indexed document in the knowledge base."""

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique document identifier",
    )
    filename: str = Field(..., description="Original filename")
    file_path: str = Field(..., description="Path on disk in KB storage")
    kb_name: str = Field(default="default", description="Knowledge base name")
    mime_type: str = Field(default="", description="MIME type of the file")
    size: int = Field(default=0, description="File size in bytes")
    status: DocumentStatus = Field(
        default=DocumentStatus.PENDING,
        description="Indexing status",
    )
    chunk_count: int = Field(default=0, description="Number of chunks")
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if status is ERROR",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 creation timestamp",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Extra document metadata",
    )


class SearchResult(BaseModel):
    """A single search result from the knowledge base."""

    document_id: str = Field(..., description="Source document ID")
    filename: str = Field(..., description="Source document filename")
    kb_name: str = Field(default="default", description="Knowledge base name")
    text: str = Field(..., description="Matching chunk text")
    score: float = Field(..., description="Relevance score (0.0–1.0)")
    chunk_id: str = Field(..., description="Chunk identifier")
    page_number: Optional[int] = Field(
        default=None,
        description="Page number if available",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata from the chunk",
    )


class SearchQuery(BaseModel):
    """Search query model for the knowledge base API."""

    query: str = Field(..., min_length=1, description="Search query text")
    kb_names: Optional[list[str]] = Field(
        default=None,
        description="Knowledge bases to search (None = all)",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum results to return",
    )
    min_score: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score",
    )


class UploadResponse(BaseModel):
    """Response model for document upload."""

    document_id: str = Field(..., description="Created document ID")
    filename: str = Field(..., description="Original filename")
    kb_name: str = Field(default="default", description="Knowledge base name")
    status: DocumentStatus = Field(..., description="Initial indexing status")
    message: str = Field(default="", description="Human-readable message")


class KnowledgeBaseInfo(BaseModel):
    """Summary information about a named knowledge base."""

    name: str = Field(..., description="Knowledge base name")
    document_count: int = Field(default=0, description="Number of documents")
    total_chunks: int = Field(default=0, description="Total chunk count")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 creation timestamp",
    )


class IndexingStatus(BaseModel):
    """Overall indexing status for a knowledge base."""

    kb_name: str = Field(default="default", description="Knowledge base name")
    total_documents: int = Field(default=0)
    ready_count: int = Field(default=0)
    indexing_count: int = Field(default=0)
    pending_count: int = Field(default=0)
    error_count: int = Field(default=0)
    total_chunks: int = Field(default=0)
    documents: list[KnowledgeDocument] = Field(default_factory=list)
