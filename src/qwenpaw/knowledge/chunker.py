# -*- coding: utf-8 -*-
"""Text chunking utilities for the knowledge base.

Splits extracted document text into overlapping chunks suitable for
embedding and semantic retrieval.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path

from .models import DocumentChunk
from .parsers import get_parser

logger = logging.getLogger(__name__)

# Characters that signal a natural split point in descending preference.
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？\n])\s+")


class TextChunker:
    """Splits text into overlapping chunks for embedding.

    Prefers splitting at paragraph boundaries, falling back to sentence
    boundaries and finally character-level splits.

    Args:
        chunk_size: Target characters per chunk (default 500).
        chunk_overlap: Characters of overlap between consecutive chunks
            (default 50).
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than "
                f"chunk_size ({chunk_size})",
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[str]:
        """Split *text* into overlapping chunks.

        Args:
            text: The full document text.

        Returns:
            List of text chunks.
        """
        if not text or not text.strip():
            return []

        # Step 1: Split into paragraphs
        paragraphs = self._split_paragraphs(text)

        # Step 2: Merge short paragraphs and split long ones
        chunks = self._build_chunks(paragraphs)

        return chunks

    def chunk_document(self, file_path: Path, document_id: str) -> list[DocumentChunk]:
        """Parse and chunk a document file.

        Args:
            file_path: Path to the document file.
            document_id: Unique identifier for the document.

        Returns:
            List of :class:`DocumentChunk` objects ready for embedding.
        """
        parser = get_parser(file_path)
        if parser is None:
            raise ValueError(
                f"No parser available for file: {file_path} "
                f"(extension: {file_path.suffix})",
            )

        text = parser.parse(file_path)
        text_chunks = self.chunk(text)

        return [
            DocumentChunk(
                document_id=document_id,
                text=chunk,
                chunk_index=i,
            )
            for i, chunk in enumerate(text_chunks)
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """Split text at paragraph boundaries, preserving section headers."""
        raw = _PARAGRAPH_BOUNDARY.split(text)
        return [p.strip() for p in raw if p.strip()]

    def _build_chunks(self, paragraphs: list[str]) -> list[str]:
        """Build overlapping chunks from paragraphs.

        Short paragraphs are merged until they reach *chunk_size*.
        Long paragraphs are split at sentence boundaries.
        """
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)

            # If adding this paragraph would exceed chunk_size, finalize
            # current chunk and start a new one.
            if current_len + para_len > self.chunk_size and current:
                chunks.append("\n\n".join(current))

                # Carry over overlap from the end of the previous chunk.
                overlap_text = self._extract_overlap(current)
                current = [overlap_text] if overlap_text else []
                current_len = len(overlap_text)

            current.append(para)
            current_len += para_len

            # If a single paragraph exceeds chunk_size, split it further.
            while current_len > self.chunk_size * 1.5:
                # Finalize what we can
                finalize = current[:-1]
                if finalize:
                    chunks.append("\n\n".join(finalize))

                # Split the oversized paragraph
                oversized = current[-1]
                parts = self._split_long_text(oversized)
                # Add all but the last part as full chunks
                for part in parts[:-1]:
                    chunks.append(part)
                # Carry the last part into the next chunk
                last_part = parts[-1] if parts else ""
                overlap_text = self._extract_overlap_text(last_part)
                current = [last_part] if last_part else []
                current_len = len(last_part)
                break  # re-evaluate from while condition

        # Don't forget the final chunk
        if current:
            chunks.append("\n\n".join(current))

        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        """Split a single long text block into chunk-sized pieces at
        sentence boundaries.
        """
        sentences = _SENTENCE_BOUNDARY.split(text)
        # Re-join with the separator that was consumed
        result: list[str] = []
        buf: list[str] = []
        buf_len = 0

        for sent in sentences:
            sent_len = len(sent)
            if buf_len + sent_len > self.chunk_size and buf:
                result.append(" ".join(buf))
                # Overlap: keep the last sentence(s)
                overlap = self._extract_overlap_text(" ".join(buf))
                buf = [overlap] if overlap else []
                buf_len = len(overlap)
            buf.append(sent)
            buf_len += sent_len

        if buf:
            result.append(" ".join(buf))

        return result or [text]

    def _extract_overlap(self, current: list[str]) -> str:
        """Extract overlap text from the end of the current chunk."""
        joined = "\n\n".join(current)
        return self._extract_overlap_text(joined)

    def _extract_overlap_text(self, text: str) -> str:
        """Extract overlap suffix from *text*."""
        if len(text) <= self.chunk_overlap:
            return text
        return text[-self.chunk_overlap :]
