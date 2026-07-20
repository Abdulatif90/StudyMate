"""Tavily live-web-search client for Research mode.

Verified contract (docs.tavily.com/documentation/api-reference/endpoint/search,
verified 2026-07-20):
- POST https://api.tavily.com/search
- Auth: `Authorization: Bearer tvly-...` header (NOT an `api_key` body field).
- Request JSON: `query`, `max_results` (0-20, default 5), `search_depth`
  ("basic"/"advanced"), `include_answer` (we keep it off — Claude synthesizes,
  not Tavily).
- Response JSON: top-level `answer` (only if `include_answer`), plus `results`,
  a list of `{title, url, content, score, ...}` objects.

ALL Tavily specifics are isolated in this module. Two failure modes, split the
same way as embedding.py / llm.py:
- Missing `TAVILY_API_KEY` is a deployment/config mistake → bare `RuntimeError`
  at point of use, so it fails loudly instead of masquerading as "no results".
- Any Tavily/network/HTTP failure → `TavilyError`, caught upstream by the
  service and degraded gracefully (never a 500 leak).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_MAX_RESULTS = 5
SEARCH_DEPTH = "basic"
_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class SearchResult:
    """One web result — the subset of Tavily's result object we surface/cite."""

    title: str
    url: str
    content: str


class TavilyError(Exception):
    """Raised when Tavily can't return search results (network/HTTP/API error)."""


def _api_key() -> str:
    settings = get_settings()
    if not settings.tavily_api_key:
        raise RuntimeError(
            "TAVILY_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return settings.tavily_api_key


def search_web(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[SearchResult]:
    """Run one Tavily search and return parsed results (title/url/content), in
    Tavily's own relevance order. Missing key → `RuntimeError`; any request/parse
    failure → `TavilyError`. Results without a `url` are skipped (nothing to cite).
    """
    api_key = _api_key()
    try:
        response = httpx.post(
            TAVILY_SEARCH_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "query": query,
                "max_results": max_results,
                "search_depth": SEARCH_DEPTH,
                "include_answer": False,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise TavilyError(f"Tavily search request failed: {exc}") from exc

    parsed: list[SearchResult] = []
    for item in payload.get("results") or []:
        url = item.get("url")
        if not url:
            continue
        parsed.append(
            SearchResult(
                title=item.get("title") or url,
                url=url,
                content=item.get("content") or "",
            )
        )
    return parsed
