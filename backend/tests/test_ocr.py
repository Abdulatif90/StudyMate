"""Unit tests for app.modules.documents.ocr — the Anthropic *client* is mocked here
(never called for real), same pattern as test_summarization.py / test_llm.py: the
base64 image block shape, response parsing, and error wrapping.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.documents import ocr
from app.modules.documents.parsing import DocumentParseError


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(ocr, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-key"))


def _fake_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_extract_text_from_image_returns_transcribed_text(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response("Line one\nLine two")
    monkeypatch.setattr(ocr.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    result = ocr.extract_text_from_image(b"\x89PNG fake bytes", "image/png")

    assert result == "Line one\nLine two"


def test_extract_text_from_image_sends_a_base64_image_block(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response("text")
    monkeypatch.setattr(ocr.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    image_bytes = b"raw image bytes"
    ocr.extract_text_from_image(image_bytes, "image/webp")

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == ocr.CLAUDE_VISION_MODEL
    content = call_kwargs["messages"][0]["content"]
    image_block = content[0]
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/webp"
    assert image_block["source"]["data"] == base64.standard_b64encode(image_bytes).decode("utf-8")
    # A verbatim-transcription instruction accompanies the image (no summarizing).
    assert content[1]["type"] == "text"
    assert "verbatim" in content[1]["text"].lower()


def test_extract_text_from_image_wraps_api_failures_as_parse_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("vision network exploded")
    monkeypatch.setattr(ocr.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    with pytest.raises(DocumentParseError):
        ocr.extract_text_from_image(b"bytes", "image/png")


def test_extract_text_from_image_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(ocr, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ocr.extract_text_from_image(b"bytes", "image/png")
