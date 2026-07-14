"""Text extraction for uploaded documents — the only place that knows how to read
PDF/DOCX/TXT bytes. Each library's own exceptions are wrapped in `DocumentParseError`
so callers only need to handle one exception type regardless of file format.

The extracted text itself isn't persisted yet (no chunking/embedding pipeline exists
until Inngest + Cohere are wired in) — for now this only proves the upload is a real,
readable document, and its outcome decides `Document.status` (ready vs. failed).
"""

from __future__ import annotations

import io

import docx
import pypdf

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT_CONTENT_TYPE = "text/plain"

SUPPORTED_CONTENT_TYPES = {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE, TXT_CONTENT_TYPE}


class DocumentParseError(Exception):
    """Raised when the uploaded file's bytes can't be parsed as text."""


def extract_text(content_type: str, raw: bytes) -> str:
    if content_type == PDF_CONTENT_TYPE:
        return _extract_pdf(raw)
    if content_type == DOCX_CONTENT_TYPE:
        return _extract_docx(raw)
    if content_type == TXT_CONTENT_TYPE:
        return _extract_txt(raw)
    raise DocumentParseError(f"Unsupported content type: {content_type}")


def _extract_pdf(raw: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise DocumentParseError(f"Could not parse PDF: {exc}") from exc


def _extract_docx(raw: bytes) -> str:
    try:
        document = docx.Document(io.BytesIO(raw))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:
        raise DocumentParseError(f"Could not parse DOCX: {exc}") from exc


def _extract_txt(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError(f"Could not decode text file as UTF-8: {exc}") from exc
