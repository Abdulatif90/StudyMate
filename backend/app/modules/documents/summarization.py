"""Claude (Anthropic) auto-summary generation for a document's extracted text.

This is documents' own concern (not ask/llm.py's) — it runs once per document during
ingest, not per question. Follows the exact same Anthropic SDK/error-handling pattern
as `app.modules.ask.llm`: missing `ANTHROPIC_API_KEY` is a deployment mistake — bare
`RuntimeError` at the point of use (same as `db.py`/`embedding.py`/`ask/llm.py`) — and
any API/network failure is wrapped in `SummarizationError` so `service.process_document`
can treat it as best-effort (log and leave `summary` NULL) rather than crashing the job.
"""

from __future__ import annotations

import anthropic

from app.core.config import get_settings
from app.shared.language import DEFAULT_LANGUAGE, language_name

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300

# Summarizing the whole text of a large document (up to the 20 MB upload limit) would
# be slow and expensive for a single background-job step; the opening portion is
# generally representative enough for a short study summary, so the input is capped
# here rather than sent in full.
MAX_INPUT_CHARS = 12_000


def _build_system_prompt(language: str) -> str:
    name = language_name(language)
    return (
        "You are StudyMate, an AI study assistant. Write a short summary (3-5 sentences) "
        "of the study material excerpt below, covering its main topics and key points, to "
        "help a student quickly recall what the document contains.\n\n"
        f"CRITICAL OUTPUT-LANGUAGE REQUIREMENT: You MUST write the entire summary in {name}. "
        f"The document's own language is irrelevant — even if the excerpt is written in a "
        f"different language, every word of your summary MUST be in {name}. Do not translate "
        f"the summary into the document's language; do not mirror the excerpt's language. "
        f"Write only in {name}.\n\n"
        "Respond with the summary text only — no preamble, no headings."
    )


def _build_user_message(excerpt: str, language: str) -> str:
    """Wrap the excerpt with a trailing target-language directive. Small models (this
    uses Claude Haiku) follow the document's dominant language over a system-only
    instruction surprisingly often, so the required output language is restated here in
    the user turn, right after the text it must NOT copy the language of.
    """
    name = language_name(language)
    return (
        f"Study material excerpt:\n\n{excerpt}\n\n"
        f"---\nWrite the 3-5 sentence summary of the excerpt above in {name}."
    )


class SummarizationError(Exception):
    """Raised when Claude can't produce a summary."""


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def summarize_document(text: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Summarize `text` (a document's extracted content) via Claude, in `language`
    (a code from `app.shared.language.SUPPORTED_LANGUAGES`, defaulting to English).
    Returns the summary text. Raises `SummarizationError` on any API/network
    failure — callers that want best-effort behavior (e.g. `service.process_document`)
    should catch it.
    """
    client = _get_client()
    excerpt = text[:MAX_INPUT_CHARS]

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(language),
            messages=[{"role": "user", "content": _build_user_message(excerpt, language)}],
        )
    except Exception as exc:
        raise SummarizationError(f"Claude summarization request failed: {exc}") from exc

    return response.content[0].text
