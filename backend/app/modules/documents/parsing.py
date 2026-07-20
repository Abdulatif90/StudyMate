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
import logging

import docx
import pypdf

logger = logging.getLogger(__name__)

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

# Scanned-PDF OCR bounds — cap how many pages/images of a text-less PDF get sent to
# Claude vision, so one big scan can't fan out into an unbounded number of (paid) vision
# calls. Mirrors the 20-page theme used elsewhere for ingest.
_MAX_OCR_PAGES = 20
_MAX_OCR_IMAGES = 20
# Claude vision's recommended max image edge; larger scans are downscaled before sending.
_MAX_IMAGE_EDGE = 1568


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
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise DocumentParseError(f"Could not parse PDF: {exc}") from exc

    if text.strip():
        return text
    # No text layer — a scanned/photographed PDF. OCR its embedded page images via Claude
    # vision (the SAME path as image uploads). If there's nothing to OCR (no embedded
    # images, or Pillow unavailable), returns "" and the document lands ready with zero
    # chunks — exactly as a text-less PDF did before this feature.
    return _ocr_pdf_pages(reader)


def _ocr_pdf_pages(reader: pypdf.PdfReader) -> str:
    """OCR a text-less PDF's embedded page images and join their transcriptions.

    Any vision/API failure surfaces as `DocumentParseError` (raised by
    `extract_text_from_image`), so a failed OCR degrades exactly like a failed PDF parse
    (status: failed, zero chunks) — never a 500.
    """
    images = _extract_page_images(reader)
    if not images:
        return ""
    # Lazy import: ocr.py imports DocumentParseError from this module, so a top-level
    # import would be circular (same reason as `extract_text`'s image branch).
    from app.modules.documents.ocr import extract_text_from_image

    transcriptions = [
        extract_text_from_image(image_bytes, content_type) for image_bytes, content_type in images
    ]
    return "\n".join(part for part in transcriptions if part)


def _extract_page_images(reader: pypdf.PdfReader) -> list[tuple[bytes, str]]:
    """Best-effort extraction of a scanned PDF's embedded page images as
    (png_bytes, "image/png") pairs ready for Claude vision.

    **Capability check + deferred requirement.** This covers the common scanned-PDF case —
    each page is a single embedded image — using only pypdf + Pillow (a lightweight pip
    wheel, no system binary). It needs Pillow to decode the images; if Pillow isn't
    installed the capability is simply OFF and this returns [] (the scanned PDF then yields
    no text: status ready, zero chunks — same as before). Full-page RASTERIZATION of a
    vector PDF that has neither a text layer nor embedded page images needs a heavy
    renderer (poppler / PyMuPDF) and is deliberately NOT added — documented as a deferred
    requirement in docs (see the OCR follow-up notes).
    """
    images: list[tuple[bytes, str]] = []
    for page_index, page in enumerate(reader.pages):
        if page_index >= _MAX_OCR_PAGES:
            break
        try:
            page_images = list(page.images)
        except Exception:
            # pypdf raises if Pillow (its image backend) is missing or an image can't be
            # decoded. Best-effort — skip this page rather than fail the whole parse.
            logger.debug("Could not read images from a PDF page (Pillow missing?)", exc_info=True)
            continue
        for image_file in page_images:
            png = _image_file_to_png(image_file)
            if png is not None:
                images.append((png, "image/png"))
            if len(images) >= _MAX_OCR_IMAGES:
                return images
    return images


def _image_file_to_png(image_file) -> bytes | None:
    """Re-encode a pypdf embedded image (a PIL image under the hood) to PNG bytes,
    downscaled to Claude vision's recommended max edge. Returns None if it can't be decoded
    (best-effort — that image is skipped)."""
    try:
        pil_image = image_file.image
        if pil_image is None:
            return None
        pil_image = pil_image.convert("RGB")
        pil_image.thumbnail((_MAX_IMAGE_EDGE, _MAX_IMAGE_EDGE))
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        logger.debug("Could not re-encode an embedded PDF image", exc_info=True)
        return None


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
