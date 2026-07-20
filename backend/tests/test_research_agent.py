"""Unit tests for app.modules.research.agent — the Anthropic *client* and Tavily's
`search_web` are both mocked, so these exercise the bounded tool-use loop itself:
the search runs, results are fed back as a `tool_result`, the final cited answer +
sources come through, the loop is hard-bounded by MAX_ITERATIONS, and the two
failure modes (missing key, Claude error) behave as documented. Fully offline.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.research import agent
from app.modules.research.tavily import SearchResult


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(
        agent, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-key")
    )


def _tool_use_response(tool_id: str, query: str):
    block = SimpleNamespace(type="tool_use", name="web_search", id=tool_id, input={"query": query})
    return SimpleNamespace(stop_reason="tool_use", content=[block])


def _final_response(text: str):
    return SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)]
    )


def _install_client(monkeypatch, fake_client):
    monkeypatch.setattr(agent.anthropic, "Anthropic", MagicMock(return_value=fake_client))


def test_loop_runs_search_then_returns_cited_answer(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _tool_use_response("toolu_1", "quantum computing 2026"),
        _final_response("Quantum computers advanced in 2026 (https://q.example)."),
    ]
    _install_client(monkeypatch, fake_client)

    found = [
        SearchResult(title="Q News", url="https://q.example", content="breakthroughs"),
    ]
    fake_search = MagicMock(return_value=found)
    monkeypatch.setattr(agent, "search_web", fake_search)

    result = agent.run_research("What happened in quantum computing?")

    # The tool actually ran with Claude's query, and the final answer + surfaced
    # sources come through.
    fake_search.assert_called_once_with("quantum computing 2026")
    assert result.answer == "Quantum computers advanced in 2026 (https://q.example)."
    assert [s.url for s in result.sources] == ["https://q.example"]

    # The second Claude call fed the search back as a tool_result matching the tool id.
    second_messages = fake_client.messages.create.call_args_list[1].kwargs["messages"]
    tool_results = [
        block
        for msg in second_messages
        if isinstance(msg.get("content"), list)
        for block in msg["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert any(tr["tool_use_id"] == "toolu_1" for tr in tool_results)


def test_loop_is_bounded_by_max_iterations(monkeypatch):
    # Claude keeps asking for tools forever — the loop must still terminate.
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _tool_use_response("toolu_x", "again")
    _install_client(monkeypatch, fake_client)

    fake_search = MagicMock(
        return_value=[SearchResult(title="T", url="https://x.example", content="c")]
    )
    monkeypatch.setattr(agent, "search_web", fake_search)

    result = agent.run_research("loop forever?")

    # Bounded: exactly MAX_ITERATIONS Claude calls, and the final permitted call
    # drops the tool so it can never keep going.
    assert fake_client.messages.create.call_count == agent.MAX_ITERATIONS
    assert "tools" not in fake_client.messages.create.call_args_list[-1].kwargs
    # Searches ran on every iteration except the tool-less final one.
    assert fake_search.call_count == agent.MAX_ITERATIONS - 1
    # Still returns a real, non-empty final answer plus what it gathered.
    assert result.answer == agent._CAP_FALLBACK_ANSWER
    assert [s.url for s in result.sources] == ["https://x.example"]


def test_missing_anthropic_key_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        agent.run_research("q")


def test_claude_failure_wrapped_as_research_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("api exploded")
    _install_client(monkeypatch, fake_client)

    with pytest.raises(agent.ResearchError):
        agent.run_research("q")
