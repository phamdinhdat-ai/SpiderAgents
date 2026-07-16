# -*- coding: utf-8 -*-
"""Knowledge base module for OpenSpider.

Provides document ingestion, semantic search, and RAG retrieval for
uploaded documents (PDF, DOCX, XLSX, Markdown, TXT).

Core components:
- :class:`KnowledgeBaseManager` — lifecycle-managed service for ingest & search
- :class:`DocumentParser` — ABC for document text extraction
- :class:`TextChunker` — splits extracted text into overlapping chunks
- :class:`VectorStore` — ABC for vector storage backends
- :class:`CrossDocumentRetriever` — multi-doc retrieval & RRF reranking
"""

from .models import (
    DocumentChunk,
    KnowledgeDocument,
    SearchResult,
    SearchQuery,
    UploadResponse,
    KnowledgeBaseInfo,
    DocumentStatus,
)
from .parsers import (
    DocumentParser,
    MarkdownParser,
    PDFParser,
    DocxParser,
    XlsxParser,
    TextParser,
    get_parser,
    parser_registry,
)
from .chunker import TextChunker
from .vector_store import VectorStore, ChromaVectorStore, LocalVectorStore
from .knowledge_base_manager import KnowledgeBaseManager
from .retrieval import CrossDocumentRetriever

__all__ = [
    # Models
    "DocumentChunk",
    "KnowledgeDocument",
    "SearchResult",
    "SearchQuery",
    "UploadResponse",
    "KnowledgeBaseInfo",
    "DocumentStatus",
    # Parsers
    "DocumentParser",
    "MarkdownParser",
    "PDFParser",
    "DocxParser",
    "XlsxParser",
    "TextParser",
    "get_parser",
    "parser_registry",
    # Chunker
    "TextChunker",
    # Vector store
    "VectorStore",
    "ChromaVectorStore",
    "LocalVectorStore",
    # Core service
    "KnowledgeBaseManager",
    # Retrieval
    "CrossDocumentRetriever",
]
