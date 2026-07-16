"""Claude (Anthropic) generation for the Ask endpoint.

Missing `ANTHROPIC_API_KEY` is a deployment mistake — raises a bare `RuntimeError` at
the point of use (same pattern as `db.py`/`auth.py`/`embedding.py`) so it fails loudly
instead of masquerading as "no answer available". Any Claude API/network failure is
wrapped in `LLMError` so callers can degrade gracefully instead of crashing the request
(see `ask/service.py`).
"""

from __future__ import annotations

from collections.abc import Iterator

import anthropic

from app.core.config import get_settings

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024

_SYSTEM_PROMPT = (
    "You are StudyMate, an AI study assistant. Answer the student's question using "
    "ONLY the excerpts provided below — never use outside knowledge, even if you "
    "know the answer. For every claim, cite the excerpt it came from in the form "
    "(filename, chunk N). If the excerpts don't contain enough information to answer "
    "the question, say so plainly instead of guessing. Always respond in the same "
    "language the student's question is written in, regardless of what language the "
    "excerpts are in."
)


class LLMError(Exception):
    """Raised when Claude can't produce an answer."""


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_messages(
    question: str,
    chunks: list[dict],
    prior_turns: list[dict] | None,
) -> list[dict]:
    """Shared by `ask_claude` and `ask_claude_stream` so both build the exact same
    prompt/history — only the *current* question carries retrieved excerpts; earlier
    turns (each a dict with `question`/`answer`) carry just their original question
    and answer, giving Claude continuity for follow-ups without re-supplying old
    sources.
    """
    excerpts = "\n\n".join(
        f"[{chunk['filename']}, chunk {chunk['chunk_index']}]\n{chunk['text']}" for chunk in chunks
    )
    user_message = f"Excerpts:\n\n{excerpts}\n\nQuestion: {question}"

    messages = []
    for turn in prior_turns or []:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def ask_claude(
    question: str,
    chunks: list[dict],
    prior_turns: list[dict] | None = None,
) -> str:
    """Ask Claude to answer `question` using only `chunks` — each a dict with
    `filename`, `chunk_index`, and `text`. Returns Claude's answer text.
    """
    client = _get_client()
    messages = _build_messages(question, chunks, prior_turns)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception as exc:
        raise LLMError(f"Claude request failed: {exc}") from exc

    return response.content[0].text


def ask_claude_stream(
    question: str,
    chunks: list[dict],
    prior_turns: list[dict] | None = None,
) -> Iterator[str]:
    """Same contract as `ask_claude` (same system prompt, same prior-turns handling,
    same excerpt/citation format), but yields the answer as text deltas instead of
    returning it whole — for the SSE streaming endpoint.

    A generator function's body doesn't run at all until first iterated, so — unlike
    `ask_claude` — errors here (including the missing-API-key `RuntimeError`) only
    surface once the caller starts consuming the stream, not at call time.
    """
    client = _get_client()
    messages = _build_messages(question, chunks, prior_turns)

    try:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            yield from stream.text_stream
    except Exception as exc:
        raise LLMError(f"Claude request failed: {exc}") from exc
