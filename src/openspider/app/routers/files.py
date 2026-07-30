# -*- coding: utf-8 -*-
from pathlib import Path
from urllib.parse import unquote
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.responses import FileResponse

router = APIRouter(prefix="/files", tags=["files"])


def _normalize_filepath(filepath: str) -> Path:
    """Normalize a URL-encoded filepath to an absolute Path."""
    normalized = unquote(filepath)

    # Normalize /C:/... to C:/... on Windows.
    if (
        len(normalized) >= 4
        and normalized[0] == "/"
        and normalized[2] == ":"
        and normalized[1].isalpha()
    ):
        normalized = normalized[1:]

    path = Path(normalized)
    if not path.is_absolute():
        path = Path("/" + normalized)
    return path.resolve()


@router.api_route(
    "/preview/{filepath:path}",
    methods=["GET", "HEAD"],
    summary="Preview file",
)
async def preview_file(
    filepath: str,
):
    """Preview file."""
    path = _normalize_filepath(filepath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, filename=path.name)


@router.get(
    "/preview-docx/{filepath:path}",
    response_class=HTMLResponse,
    summary="Preview DOCX file as HTML",
)
async def preview_docx(
    filepath: str,
    request: Request,
):
    """Convert a DOCX file to HTML for in-browser preview.

    Uses python-docx to extract paragraphs, tables, and basic formatting.
    Falls back to plain text if conversion fails.
    """
    path = _normalize_filepath(filepath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    ext = path.suffix.lower()
    if ext not in (".docx",):
        raise HTTPException(
            status_code=415,
            detail=f"DOCX preview only supports .docx files, got {ext}",
        )

    try:
        from docx import Document  # type: ignore[import-untyped]

        doc = Document(str(path))

        html_parts: list[str] = ['<div class="docx-preview">']

        for para in doc.paragraphs:
            text = para.text or ""
            if not text.strip():
                html_parts.append("<p>&nbsp;</p>")
                continue

            # Detect heading style
            style_name = (para.style.name if para.style else "").lower()
            if style_name.startswith("heading"):
                level = style_name.replace("heading", "").strip()
                try:
                    lv = int(level)
                except ValueError:
                    lv = 2
                lv = max(1, min(6, lv))
                html_parts.append(f"<h{lv}>{_escape_html(text)}</h{lv}>")
            else:
                # Inline formatting
                runs_html: list[str] = []
                for run in para.runs:
                    t = _escape_html(run.text or "")
                    if not t:
                        continue
                    if run.bold:
                        t = f"<strong>{t}</strong>"
                    if run.italic:
                        t = f"<em>{t}</em>"
                    if run.underline:
                        t = f"<u>{t}</u>"
                    runs_html.append(t)
                html_parts.append(f"<p>{''.join(runs_html) if runs_html else _escape_html(text)}</p>")

        # Tables
        for table in doc.tables:
            html_parts.append('<table class="docx-table">')
            for row in table.rows:
                html_parts.append("<tr>")
                for cell in row.cells:
                    html_parts.append(f"<td>{_escape_html(cell.text or '')}</td>")
                html_parts.append("</tr>")
            html_parts.append("</table>")

        html_parts.append("</div>")
        return HTMLResponse(content="\n".join(html_parts))

    except Exception as exc:
        # Fallback: return plain text wrapped in <pre>
        try:
            from docx import Document

            doc = Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs if p.text)
            return HTMLResponse(
                content=f'<pre class="docx-fallback">{_escape_html(text)}</pre>'
            )
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read DOCX file: {exc}",
            )


@router.delete(
    "/{filepath:path}",
    summary="Delete a file from the workspace",
)
async def delete_file(
    filepath: str,
    request: Request,
):
    """Delete a file.

    The file must be within the agent's workspace directory.
    """
    path = _normalize_filepath(filepath)

    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: verify the file is within a workspace-like directory.
    # We check that the path contains "workspace" as a heuristic, since
    # the full workspace resolution requires agent context unavailable here.
    path_str = str(path).lower()
    if "workspace" not in path_str:
        raise HTTPException(
            status_code=403,
            detail="File must be within a workspace directory",
        )

    try:
        path.unlink()
        return {"status": "deleted", "filepath": str(path)}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}")


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
