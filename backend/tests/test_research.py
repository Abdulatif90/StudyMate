"""Tests for the Research endpoint (app.modules.research) — router + service via
TestClient. `run_research` (the agentic loop) is mocked, so these exercise the HTTP
wiring and, crucially, the graceful-degradation contract: a Claude failure and a
failed search both return a normal 200 ResearchResponse with an explanatory answer,
never an HTTP error. Fully offline.

A single `live` test at the bottom hits real Tavily + Claude — deselected by default
(`pytest -m live`), and skipped unless both keys are configured.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.main import app
from app.modules.research import service
from app.modules.research.agent import ResearchError, ResearchResult
from app.modules.research.tavily import SearchResult, TavilyError

_TEST_USER = "user_test_research"


@pytest.fixture(autouse=True)
def _auth_override():
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    yield
    del app.dependency_overrides[get_current_user_id]


@pytest.fixture()
def client():
    return TestClient(app)


def test_research_returns_answer_and_sources(monkeypatch, client):
    monkeypatch.setattr(
        service,
        "run_research",
        lambda query: ResearchResult(
            answer="The web says X (https://s.example).",
            sources=[SearchResult(title="Src", url="https://s.example", content="c")],
        ),
    )

    response = client.post("/research", json={"query": "what is X?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "The web says X (https://s.example)."
    assert body["sources"] == [{"title": "Src", "url": "https://s.example"}]


def test_empty_sources_still_returns_200_answer(monkeypatch, client):
    monkeypatch.setattr(
        service,
        "run_research",
        lambda query: ResearchResult(answer="I found nothing relevant on the web.", sources=[]),
    )

    response = client.post("/research", json={"query": "obscure question"})

    assert response.status_code == 200
    assert response.json() == {"answer": "I found nothing relevant on the web.", "sources": []}


def test_claude_failure_degrades_to_200(monkeypatch, client):
    def _boom(query):
        raise ResearchError("claude down")

    monkeypatch.setattr(service, "run_research", _boom)

    response = client.post("/research", json={"query": "anything"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert body["answer"] == service._DEGRADED_ANSWER


def test_search_failure_degrades_to_200(monkeypatch, client):
    def _boom(query):
        raise TavilyError("tavily down")

    monkeypatch.setattr(service, "run_research", _boom)

    response = client.post("/research", json={"query": "anything"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert body["answer"] == service._DEGRADED_ANSWER


@pytest.mark.live
@pytest.mark.skipif(
    not (get_settings().tavily_api_key and get_settings().anthropic_api_key),
    reason="needs real TAVILY_API_KEY + ANTHROPIC_API_KEY",
)
def test_research_live_end_to_end():
    result = service.research("What is the James Webb Space Telescope known for?")
    # Real run: not the degraded fallback, and at least one live source surfaced.
    assert result.answer and result.answer != service._DEGRADED_ANSWER
    assert len(result.sources) >= 1
    assert all(s.url.startswith("http") for s in result.sources)
