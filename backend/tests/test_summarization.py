"""Unit tests for app.modules.documents.summarization — the Anthropic *client* is
mocked here (not our own summarize_document wrapper), same pattern as test_llm.py:
call shape/system prompt, response parsing, and error wrapping.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.documents import summarization


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(
        summarization, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-key")
    )


def _fake_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_summarize_document_returns_response_text(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response("A short summary.")
    monkeypatch.setattr(summarization.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    result = summarization.summarize_document("Photosynthesis converts sunlight into energy.")

    assert result == "A short summary."
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == summarization.CLAUDE_MODEL
    assert call_kwargs["system"] == summarization._SYSTEM_PROMPT
    assert call_kwargs["messages"][0]["content"] == "Photosynthesis converts sunlight into energy."


def test_summarize_document_truncates_long_input(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response("summary")
    monkeypatch.setattr(summarization.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    long_text = "x" * (summarization.MAX_INPUT_CHARS + 500)
    summarization.summarize_document(long_text)

    sent_content = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert len(sent_content) == summarization.MAX_INPUT_CHARS


def test_summarize_document_wraps_api_failures(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("network exploded")
    monkeypatch.setattr(summarization.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    with pytest.raises(summarization.SummarizationError):
        summarization.summarize_document("some text")


def test_summarize_document_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(
        summarization, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None)
    )

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        summarization.summarize_document("some text")
