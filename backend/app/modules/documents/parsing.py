"""Text extraction for uploaded documents — the only place that knows how to read
PDF/DOCX/TXT bytes and, for photographed/scanned notes, image bytes (via Claude vision
OCR — see `ocr.py`). Each library's / the vision API's own exceptions are wrapped in
`DocumentParseError` so callers only need to handle one exception type regardless of
file format.

The extracted text (whatever the source) feeds the same chunk → embed → summarize
pipeline, and its outcome decides `Document.status` (ready vs. failed).
"""

from __future__ import annotations

import io

import docx
import pypdf

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT_CONTENT_TYPE = "text/plain"
# Image types transcribed via Claude vision (`ocr.py`). Kept in sync with
# `ocr.SUPPORTED_IMAGE_CONTENT_TYPES` — the media types the vision API accepts.
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

SUPPORTED_CONTENT_TYPES = {
    PDF_CONTENT_TYPE,
    DOCX_CONTENT_TYPE,
    TXT_CONTENT_TYPE,
    *IMAGE_CONTENT_TYPES,
}


class DocumentParseError(Exception):
    """Raised when the uploaded file's bytes can't be parsed as text."""


def extract_text(content_type: str, raw: bytes) -> str:
    if content_type == PDF_CONTENT_TYPE:
        return _extract_pdf(raw)
    if content_type == DOCX_CONTENT_TYPE:
        return _extract_docx(raw)
    if content_type == TXT_CONTENT_TYPE:
        return _extract_txt(raw)
    if content_type in IMAGE_CONTENT_TYPES:
        # Imported lazily: ocr.py imports DocumentParseError from this module, so a
        # top-level import would be circular. OCR is just another parse branch — its
        # DocumentParseError on failure keeps the "failed parse → status: failed, zero
        # chunks" invariant, same as the PDF/DOCX paths above.
        from app.modules.documents.ocr import extract_text_from_image

        return extract_text_from_image(raw, content_type)
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
