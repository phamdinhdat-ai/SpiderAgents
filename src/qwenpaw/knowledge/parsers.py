# -*- coding: utf-8 -*-
"""Document parsers for extracting text from various file formats.

Each parser implements :class:`DocumentParser` and registers against
one or more file extensions via :attr:`parser_registry`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from ..agents.utils.registry import Registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

parser_registry: Registry["DocumentParser"] = Registry()


# ---------------------------------------------------------------------------
# Abstract base parser
# ---------------------------------------------------------------------------


class DocumentParser(ABC):
    """Abstract base class for document text extraction.

    Subclasses register for one or more file extensions and implement
    :meth:`parse` to return the extracted plain-text content.
    """

    @abstractmethod
    def parse(self, file_path: Path) -> str:
        """Extract plain text from *file_path*.

        Args:
            file_path: Absolute path to the document.

        Returns:
            Extracted text content.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            ValueError: If the file cannot be parsed.
        """

    @property
    @abstractmethod
    def supported_extensions(self) -> frozenset[str]:
        """File extensions this parser handles (lowercase, with dot)."""


# ---------------------------------------------------------------------------
# Concrete parsers
# ---------------------------------------------------------------------------


@parser_registry.register(".txt")
class TextParser(DocumentParser):
    """Plain text file parser."""

    supported_extensions: frozenset[str] = frozenset({".txt", ".log", ".csv", ".tsv"})

    def parse(self, file_path: Path) -> str:
        """Read plain text with encoding fallback."""
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="latin-1")


@parser_registry.register(".md")
class MarkdownParser(DocumentParser):
    """Markdown file parser.

    Strips YAML frontmatter (``---`` delimited) before returning content.
    """

    supported_extensions: frozenset[str] = frozenset({".md", ".markdown"})

    def parse(self, file_path: Path) -> str:
        """Read markdown, stripping frontmatter."""
        text = file_path.read_text(encoding="utf-8")
        return self._strip_frontmatter(text)

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        """Remove YAML frontmatter delimited by ``---``."""
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return text

        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :]).strip()
        # No closing delimiter — return as-is
        return text


@parser_registry.register(".pdf")
class PDFParser(DocumentParser):
    """PDF text extraction using pypdf / pdfplumber.

    Tries *pdfplumber* first (better table / layout preservation),
    falling back to *pypdf*.
    """

    supported_extensions: frozenset[str] = frozenset({".pdf"})

    def parse(self, file_path: Path) -> str:
        """Extract text from a PDF file."""
        text = self._parse_with_pdfplumber(file_path)
        if text.strip():
            return text
        return self._parse_with_pypdf(file_path)

    @staticmethod
    def _parse_with_pdfplumber(file_path: Path) -> str:
        """Extract via pdfplumber (good for tables and layout)."""
        try:
            import pdfplumber
        except ImportError:
            logger.debug("pdfplumber not installed, skipping")
            return ""

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                pages: list[str] = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages.append(page_text)
                return "\n\n".join(pages)
        except Exception as exc:
            logger.warning("pdfplumber failed for %s: %s", file_path, exc)
            return ""

    @staticmethod
    def _parse_with_pypdf(file_path: Path) -> str:
        """Extract via pypdf (simple but reliable)."""
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError(
                "Neither pdfplumber nor pypdf is installed. "
                "Install one: pip install pypdf pdfplumber",
            ) from None

        reader = PdfReader(str(file_path))
        pages: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)
        return "\n\n".join(pages)


@parser_registry.register(".docx")
class DocxParser(DocumentParser):
    """DOCX text extraction using python-docx."""

    supported_extensions: frozenset[str] = frozenset({".docx"})

    def parse(self, file_path: Path) -> str:
        """Extract text from a DOCX file."""
        try:
            from docx import Document  # python-docx
        except ImportError:
            raise ValueError(
                "python-docx is not installed. "
                "Install it: pip install python-docx",
            ) from None

        try:
            doc = Document(str(file_path))
            paragraphs: list[str] = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text)

            # Also extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    cells = [
                        cell.text.strip()
                        for cell in row.cells
                        if cell.text.strip()
                    ]
                    if cells:
                        paragraphs.append(" | ".join(cells))

            return "\n\n".join(paragraphs)
        except Exception as exc:
            raise ValueError(f"Failed to parse DOCX: {exc}") from exc


@parser_registry.register(".xlsx")
class XlsxParser(DocumentParser):
    """XLSX text extraction using openpyxl."""

    supported_extensions: frozenset[str] = frozenset({".xlsx", ".xlsm"})

    def parse(self, file_path: Path) -> str:
        """Extract text from an XLSX file, flattening all sheets."""
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ValueError(
                "openpyxl is not installed. "
                "Install it: pip install openpyxl",
            ) from None

        try:
            wb = load_workbook(str(file_path), read_only=True, data_only=True)
            output: list[str] = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                output.append(f"## Sheet: {sheet_name}")
                rows: list[str] = []
                for row in ws.iter_rows(values_only=True):
                    cells = [
                        str(cell) if cell is not None else ""
                        for cell in row
                    ]
                    # Skip completely empty rows
                    if any(cells):
                        rows.append("\t".join(cells))
                output.append("\n".join(rows))
                output.append("")
            wb.close()
            return "\n".join(output)
        except Exception as exc:
            raise ValueError(f"Failed to parse XLSX: {exc}") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_parser(file_path: Path) -> DocumentParser | None:
    """Return the appropriate parser for *file_path* based on its suffix.

    Args:
        file_path: Path to the document.

    Returns:
        A :class:`DocumentParser` instance, or ``None`` if no parser
        is registered for the file's extension.
    """
    suffix = file_path.suffix.lower()
    parser_cls = parser_registry.get(suffix)
    if parser_cls is None:
        logger.debug("No parser registered for extension: %s", suffix)
        return None
    return parser_cls()
