"""The bounded agentic tool-use loop for Research mode.

Claude (`claude-opus-4-8`, the current recommended model per the claude-api skill)
runs a manual tool-use loop with a single custom `web_search` tool backed by
Tavily. Loop shape (confirmed against the claude-api skill's manual-loop pattern):
call `messages.create(tools=[...])`; while `stop_reason == "tool_use"`, execute the
requested search(es), append the assistant turn plus one `tool_result` block per
call, and call again — until Claude returns a final text answer.

Safety: a hard `MAX_ITERATIONS` cap bounds the number of Claude calls so the loop
can never run away. The final permitted iteration is made WITHOUT the tool, forcing
Claude to synthesize a final answer from what it already gathered instead of asking
for yet another search.

Failure modes mirror ask/llm.py:
- Missing `ANTHROPIC_API_KEY` → bare `RuntimeError` at point of use (deploy mistake).
- Any Claude API/network failure → `ResearchError`, caught by the service and
  degraded to a clear message (never a 500 leak).
A `TavilyError` from `search_web` propagates out of the loop for the service to
degrade — the same graceful-degradation contract lives in one place (service.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from app.core.config import get_settings
from app.modules.research.tavily import SearchResult, search_web

CLAUDE_MODEL = "claude-opus-4-8"
MAX_TOKENS = 2048
# Hard cap on Claude calls in the loop — the runaway-prevention guarantee. The last
# permitted call drops the tool so Claude must produce a final answer.
MAX_ITERATIONS = 5

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the live web for current, factual information that goes beyond the "
        "user's own study materials. Returns a list of results with titles, URLs, and "
        "content snippets. Call this one or more times to gather what you need before "
        "writing your final answer."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to run against the live web.",
            }
        },
        "required": ["query"],
    },
}

_SYSTEM_PROMPT = (
    "You are StudyMate's research assistant. Answer the user's question using live web "
    "search that goes BEYOND any uploaded study materials. Use the web_search tool to "
    "find current, relevant information before answering — you may search more than once "
    "to refine or broaden your research. Once you have enough, write a clear, "
    "well-structured answer and cite the source URLs you actually used inline. If your "
    "searches don't turn up enough to answer, say so plainly instead of guessing. Always "
    "respond in the same language as the user's question."
)

# Used only when the loop's hard cap is reached and Claude still produced no final
# text (e.g. it kept asking for tools). We return what we gathered rather than nothing.
_CAP_FALLBACK_ANSWER = (
    "I gathered information from the web but reached my research step limit before "
    "finishing a full synthesis. The sources I consulted are listed below."
)


@dataclass(frozen=True)
class ResearchResult:
    answer: str
    sources: list[SearchResult]


class ResearchError(Exception):
    """Raised when Claude can't drive the research loop to a final answer."""


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _call_claude(client: anthropic.Anthropic, messages: list[dict], *, allow_tools: bool):
    kwargs = {
        "model": CLAUDE_MODEL,
        "max_tokens": MAX_TOKENS,
        "system": _SYSTEM_PROMPT,
        "messages": messages,
    }
    if allow_tools:
        kwargs["tools"] = [WEB_SEARCH_TOOL]
    try:
        return client.messages.create(**kwargs)
    except Exception as exc:
        raise ResearchError(f"Claude request failed: {exc}") from exc


def _extract_text(response) -> str:
    parts = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    return "\n".join(parts).strip()


def _run_tool_calls(response, sources: dict[str, SearchResult]) -> list[dict]:
    """Execute every `web_search` tool call in the assistant turn, record the
    surfaced sources (deduped by URL, insertion-ordered), and build the matching
    `tool_result` blocks. A `TavilyError` raised by `search_web` propagates — the
    service degrades it; we don't swallow it here.
    """
    tool_results: list[dict] = []
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if block.name != WEB_SEARCH_TOOL["name"]:
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Unknown tool: {block.name}",
                    "is_error": True,
                }
            )
            continue
        query = (block.input or {}).get("query", "")
        results = search_web(query)
        for result in results:
            sources[result.url] = result
        tool_results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _format_results(results),
            }
        )
    return tool_results


def _format_results(results: list[SearchResult]) -> str:
    if not results:
        return "No results found."
    return "\n\n".join(
        f"[{i}] {result.title}\nURL: {result.url}\n{result.content}"
        for i, result in enumerate(results, start=1)
    )


def run_research(query: str) -> ResearchResult:
    """Drive the bounded tool-use loop and return the final answer plus the sources
    Claude actually surfaced. Missing key → `RuntimeError`; Claude failure →
    `ResearchError`; Tavily failure → `TavilyError` (all handled upstream).
    """
    client = _get_client()
    messages: list[dict] = [{"role": "user", "content": query}]
    # url -> SearchResult; dict preserves first-seen order and dedupes across searches.
    sources: dict[str, SearchResult] = {}

    for iteration in range(MAX_ITERATIONS):
        is_last = iteration == MAX_ITERATIONS - 1
        response = _call_claude(client, messages, allow_tools=not is_last)

        if is_last or response.stop_reason != "tool_use":
            answer = _extract_text(response) or _CAP_FALLBACK_ANSWER
            return ResearchResult(answer=answer, sources=list(sources.values()))

        # Tool use requested and iterations remain: run the searches, feed results back.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": _run_tool_calls(response, sources)})

    # Unreachable in practice — the last iteration always returns above — but a
    # defensive final answer keeps the function total.
    return ResearchResult(answer=_CAP_FALLBACK_ANSWER, sources=list(sources.values()))
