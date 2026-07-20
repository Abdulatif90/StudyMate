"""Unit tests for app.modules.documents.parsing — focused on the scanned-PDF OCR path
added for text-less (image-only) PDFs. Claude vision (`extract_text_from_image`) is ALWAYS
mocked here; the embedded-image extraction (pypdf + Pillow) runs for real against a fixture
PDF built with Pillow, so the actual scanned-PDF → image → OCR wiring is exercised.
"""

from __future__ import annotations

import io

import pypdf
import pytest
from PIL import Image

from app.modules.documents import ocr, parsing
from app.modules.documents.parsing import DocumentParseError

# A minimal hand-crafted PDF that DOES carry a real text layer (pypdf extracts "Hello PDF"
# from it). Used to prove a text-bearing PDF is never sent down the OCR path.
_TEXT_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R
/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 24 Tf 20 100 Td (Hello PDF) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
trailer<</Root 1 0 R/Size 6>>
startxref
0
%%EOF"""


def _scanned_pdf(pages: int = 1) -> bytes:
    """A text-less PDF whose page(s) are a single embedded image — i.e. what a scan looks
    like. Built with Pillow (which embeds the image and adds NO text layer), so pypdf reads
    back empty text + one image per page."""
    imgs = [Image.new("RGB", (300, 200), (255, 255, 255)) for _ in range(pages)]
    buffer = io.BytesIO()
    imgs[0].save(buffer, format="PDF", save_all=True, append_images=imgs[1:])
    return buffer.getvalue()


def _blank_pdf() -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_text_pdf_returns_text_and_never_ocrs(monkeypatch):
    called = False

    def _spy(reader):
        nonlocal called
        called = True
        return "SHOULD NOT HAPPEN"

    monkeypatch.setattr(parsing, "_ocr_pdf_pages", _spy)

    result = parsing.extract_text("application/pdf", _TEXT_PDF)

    assert "Hello PDF" in result
    assert called is False  # a text layer short-circuits before any OCR


def test_scanned_pdf_ocrs_its_page_image(monkeypatch):
    # Real embedded-image extraction (pypdf + Pillow); only the vision call is mocked.
    monkeypatch.setattr(
        ocr, "extract_text_from_image", lambda image_bytes, content_type: "transcribed scan"
    )

    result = parsing.extract_text("application/pdf", _scanned_pdf())

    assert result == "transcribed scan"


def test_scanned_pdf_joins_multiple_pages(monkeypatch):
    monkeypatch.setattr(
        ocr, "extract_text_from_image", lambda image_bytes, content_type: "page text"
    )

    result = parsing.extract_text("application/pdf", _scanned_pdf(pages=3))

    assert result.split("\n") == ["page text", "page text", "page text"]


def test_scanned_pdf_ocr_failure_raises_parse_error(monkeypatch):
    def _raise(image_bytes, content_type):
        raise DocumentParseError("vision exploded")

    monkeypatch.setattr(ocr, "extract_text_from_image", _raise)

    with pytest.raises(DocumentParseError):
        parsing.extract_text("application/pdf", _scanned_pdf())


def test_textless_pdf_with_no_images_returns_empty(monkeypatch):
    # A blank PDF has neither text nor embedded images → nothing to OCR, empty result (the
    # document lands ready with zero chunks, same as before this feature). OCR never called.
    def _fail(*args, **kwargs):
        raise AssertionError("OCR must not be attempted when there are no images")

    monkeypatch.setattr(ocr, "extract_text_from_image", _fail)

    assert parsing.extract_text("application/pdf", _blank_pdf()) == ""


def test_pillow_unavailable_degrades_to_empty(monkeypatch):
    # Capability check: if the embedded images can't be decoded (Pillow missing / undecodable
    # image), _image_file_to_png returns None for each → no images → empty result, no OCR.
    monkeypatch.setattr(parsing, "_image_file_to_png", lambda image_file: None)

    def _fail(*args, **kwargs):
        raise AssertionError("OCR must not be attempted when no images could be decoded")

    monkeypatch.setattr(ocr, "extract_text_from_image", _fail)

    assert parsing.extract_text("application/pdf", _scanned_pdf()) == ""
