"""Unit tests for app.modules.ask.llm — the Anthropic *client* is mocked here (not
our own ask_claude wrapper), so these exercise ask_claude's own logic: the call
shape/system prompt, response parsing, and error wrapping.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.ask import llm


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-key"))


def _fake_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_ask_claude_returns_response_text(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response("The answer is 42.")
    monkeypatch.setattr(llm.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    chunks = [{"filename": "notes.txt", "chunk_index": 0, "text": "Some excerpt."}]
    result = llm.ask_claude("What is the answer?", chunks)

    assert result == "The answer is 42."
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == llm.CLAUDE_MODEL
    assert call_kwargs["system"] == llm._SYSTEM_PROMPT
    user_content = call_kwargs["messages"][0]["content"]
    assert "notes.txt, chunk 0" in user_content
    assert "Some excerpt." in user_content
    assert "What is the answer?" in user_content


def test_ask_claude_wraps_api_failures(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("network exploded")
    monkeypatch.setattr(llm.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    with pytest.raises(llm.LLMError):
        llm.ask_claude("question", [{"filename": "f.txt", "chunk_index": 0, "text": "x"}])


def test_ask_claude_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.ask_claude("question", [])


class _FakeStreamContextManager:
    """Stands in for `client.messages.stream(...)`'s return value — a context
    manager whose `__enter__` yields an object exposing `.text_stream`, matching
    the real Anthropic SDK's `MessageStreamManager`/`MessageStream`.
    """

    def __init__(self, deltas):
        self._deltas = deltas

    def __enter__(self):
        return SimpleNamespace(text_stream=iter(self._deltas))

    def __exit__(self, *_args):
        return False


def test_ask_claude_stream_yields_text_deltas(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.stream.return_value = _FakeStreamContextManager(["Hello", " world"])
    monkeypatch.setattr(llm.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    chunks = [{"filename": "notes.txt", "chunk_index": 0, "text": "Some excerpt."}]
    result = list(llm.ask_claude_stream("What is the answer?", chunks))

    assert result == ["Hello", " world"]
    call_kwargs = fake_client.messages.stream.call_args.kwargs
    assert call_kwargs["model"] == llm.CLAUDE_MODEL
    assert call_kwargs["system"] == llm._SYSTEM_PROMPT
    user_content = call_kwargs["messages"][0]["content"]
    assert "notes.txt, chunk 0" in user_content
    assert "Some excerpt." in user_content
    assert "What is the answer?" in user_content


def test_ask_claude_stream_wraps_api_failures_before_any_delta(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = RuntimeError("network exploded")
    monkeypatch.setattr(llm.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    with pytest.raises(llm.LLMError):
        list(
            llm.ask_claude_stream(
                "question", [{"filename": "f.txt", "chunk_index": 0, "text": "x"}]
            )
        )


def test_ask_claude_stream_wraps_failures_partway_through(monkeypatch):
    def _erroring_deltas():
        yield "Hel"
        yield "lo"
        raise RuntimeError("connection dropped")

    fake_client = MagicMock()
    fake_client.messages.stream.return_value = _FakeStreamContextManager(_erroring_deltas())
    monkeypatch.setattr(llm.anthropic, "Anthropic", MagicMock(return_value=fake_client))

    gen = llm.ask_claude_stream("question", [{"filename": "f.txt", "chunk_index": 0, "text": "x"}])
    assert next(gen) == "Hel"
    assert next(gen) == "lo"
    with pytest.raises(llm.LLMError):
        next(gen)


def test_ask_claude_stream_raises_runtime_error_only_on_first_iteration(monkeypatch):
    # A generator function's body doesn't run until first iterated — the missing-key
    # RuntimeError must not surface merely from calling ask_claude_stream(...).
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))

    gen = llm.ask_claude_stream("question", [])
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        next(gen)
