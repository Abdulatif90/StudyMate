"""Unit tests for app.modules.research.tavily — the HTTP layer (`httpx.post`) is
mocked, so these exercise our own contract: request shape (Bearer auth + JSON body),
response parsing, error wrapping, and the missing-key RuntimeError. Fully offline.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.research import tavily


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(tavily, "get_settings", lambda: SimpleNamespace(tavily_api_key="tvly-test"))


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_search_web_parses_results(monkeypatch):
    payload = {
        "answer": "ignored",
        "results": [
            {"title": "First", "url": "https://a.example/1", "content": "snippet one"},
            {"title": "Second", "url": "https://b.example/2", "content": "snippet two"},
            {"title": "No URL", "content": "dropped — nothing to cite"},
        ],
    }
    fake_post = MagicMock(return_value=_FakeResponse(payload))
    monkeypatch.setattr(tavily.httpx, "post", fake_post)

    results = tavily.search_web("photosynthesis", max_results=5)

    # The URL-less result is skipped; the other two parse in order.
    assert [r.url for r in results] == ["https://a.example/1", "https://b.example/2"]
    assert results[0].title == "First"
    assert results[0].content == "snippet one"

    call = fake_post.call_args
    assert call.args[0] == tavily.TAVILY_SEARCH_URL
    assert call.kwargs["headers"]["Authorization"] == "Bearer tvly-test"
    body = call.kwargs["json"]
    assert body["query"] == "photosynthesis"
    assert body["max_results"] == 5
    assert body["include_answer"] is False


def test_search_web_wraps_failures_as_tavily_error(monkeypatch):
    monkeypatch.setattr(
        tavily.httpx, "post", MagicMock(side_effect=RuntimeError("network exploded"))
    )

    with pytest.raises(tavily.TavilyError):
        tavily.search_web("query")


def test_search_web_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(tavily, "get_settings", lambda: SimpleNamespace(tavily_api_key=None))

    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        tavily.search_web("query")
