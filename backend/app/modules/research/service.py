"""Research orchestration — runs the agentic loop and shapes the response.

ALL graceful degradation lives here so the router stays thin. A failed/aborted
search (`TavilyError`) or a Claude failure (`ResearchError`) both degrade to a
normal 200 `ResearchResponse` with an explanatory answer and empty sources — never
an HTTP 5xx. The missing-key `RuntimeError` from the clients is deliberately NOT
caught: an unset key is a deployment mistake that must fail loudly (a genuine 500),
matching the loud-failure pattern used across the app.

TODO (later increment): combine live web results with the user's own uploaded RAG
documents (this increment is web-only), and persist research sessions like Ask does.
"""

from __future__ import annotations

from app.modules.research.agent import ResearchError, run_research
from app.modules.research.schemas import ResearchResponse, ResearchSource
from app.modules.research.tavily import TavilyError

_DEGRADED_ANSWER = (
    "I couldn't complete live web research for that question right now. "
    "Please try again in a moment."
)


def research(query: str) -> ResearchResponse:
    try:
        result = run_research(query)
    except (TavilyError, ResearchError):
        return ResearchResponse(answer=_DEGRADED_ANSWER, sources=[])

    return ResearchResponse(
        answer=result.answer,
        sources=[ResearchSource(title=source.title, url=source.url) for source in result.sources],
    )
