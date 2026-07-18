"""Claude flashcard generation via **tool-use structured output** (DECISIONS.md #5, same
approach as `quiz/generation.py`): flashcard JSON comes back as a validated tool call,
never `json.loads` on free-text prose.

Claude is given a single `record_flashcards` tool with a strict `input_schema` and
forced to call it (`tool_choice`), so the response is a `tool_use` block whose `.input`
is a dict the API already shaped to the schema. Still validated defensively here, and
any violation — or an API/network failure, or a response that isn't a tool call —
becomes a `FlashcardGenerationError`.

Same Anthropic SDK / error-handling family as `ask/llm.py`, `documents/summarization.py`,
and `quiz/generation.py`: missing `ANTHROPIC_API_KEY` is a deployment mistake, so it
raises a bare `RuntimeError` at the point of use; a per-request failure is wrapped so the
caller (`service.generate_flashcards`) can surface a clean error instead of crashing.
Multilingual: the caller passes a target `language` code (see `app.shared.language`)
and the prompt tells Claude to write in that language regardless of the source
material's own language (same approach as summary/ask/quiz).
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from app.core.config import get_settings
from app.shared.language import DEFAULT_LANGUAGE, language_name

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# The tool Claude is forced to call. Its input_schema is the contract: a `flashcards`
# array, each with a front (question/prompt/term) and a back (answer/definition).
# `additionalProperties: false` + `required` keep Claude from drifting the shape — this
# is the structured-output boundary, nothing downstream parses prose.
FLASHCARD_TOOL_NAME = "record_flashcards"
_FLASHCARD_TOOL = {
    "name": FLASHCARD_TOOL_NAME,
    "description": ("Record the generated flashcards. Call this exactly once with all the cards."),
    "input_schema": {
        "type": "object",
        "properties": {
            "flashcards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "front": {
                            "type": "string",
                            "description": "The prompt side — a question, term, or concept.",
                        },
                        "back": {
                            "type": "string",
                            "description": "The answer side — the definition or explanation.",
                        },
                    },
                    "required": ["front", "back"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["flashcards"],
        "additionalProperties": False,
    },
}


class FlashcardGenerationError(Exception):
    """Raised when Claude can't produce well-formed flashcards."""


@dataclass(frozen=True)
class GeneratedFlashcard:
    """One validated front/back pair from the tool response — shape already checked
    (both sides are non-empty strings), ready for the service to persist without
    re-validating."""

    front: str
    back: str


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_system_prompt(num_cards: int, language: str) -> str:
    return (
        "You are StudyMate, an AI study assistant. Using ONLY the study material "
        f"excerpts provided, write {num_cards} flashcards that test recall of the "
        "material's key facts, terms, and concepts. Each card has a short `front` "
        "(a question, term, or concept) and a concise `back` (the answer or "
        f"definition) — keep both sides brief enough to read at a glance. Write the "
        f"front and back in {language_name(language)}, regardless of what language the "
        "source material is written in. Do not use outside knowledge. Return the cards "
        f"by calling the `{FLASHCARD_TOOL_NAME}` tool — do not write any prose."
    )


def _extract_tool_input(response: anthropic.types.Message) -> dict:
    """Pull the forced tool call's `.input` (a dict) out of the response, or raise
    `FlashcardGenerationError` if — despite `tool_choice` forcing it — no tool_use block
    is present (e.g. the model hit max_tokens mid-call and returned a partial/other
    block)."""
    for block in response.content:
        if block.type == "tool_use" and block.name == FLASHCARD_TOOL_NAME:
            return block.input
    raise FlashcardGenerationError("Claude did not return a flashcards tool call")


def _parse_flashcards(tool_input: dict) -> list[GeneratedFlashcard]:
    """Validate the tool input into `GeneratedFlashcard`s. Defensive even though the API
    shaped it to the schema — an empty-string front/back would satisfy `"type": "string"`
    but is useless as a card."""
    raw_cards = tool_input.get("flashcards")
    if not isinstance(raw_cards, list) or not raw_cards:
        raise FlashcardGenerationError("Flashcards tool call contained no cards")

    cards: list[GeneratedFlashcard] = []
    for raw in raw_cards:
        front = raw.get("front")
        back = raw.get("back")

        if not isinstance(front, str) or not front.strip():
            raise FlashcardGenerationError("A flashcard was missing its front")
        if not isinstance(back, str) or not back.strip():
            raise FlashcardGenerationError("A flashcard was missing its back")

        cards.append(GeneratedFlashcard(front=front, back=back))
    return cards


def generate_flashcard_set(
    excerpts: list[str], num_cards: int, language: str = DEFAULT_LANGUAGE
) -> list[GeneratedFlashcard]:
    """Generate `num_cards` flashcards from `excerpts` (a subject's retrieved chunk
    texts) via Claude tool-use, written in `language` (a code from
    `app.shared.language.SUPPORTED_LANGUAGES`, defaulting to English). Returns
    validated `GeneratedFlashcard`s. Raises `FlashcardGenerationError` on any API
    failure or malformed/empty response.
    """
    if not excerpts:
        raise FlashcardGenerationError("No material to generate flashcards from")

    client = _get_client()
    material = "\n\n---\n\n".join(excerpts)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            # Budget scales with card count; each front/back pair is short (a fraction
            # of a quiz question + explanation). Bounded so a huge num_cards can't
            # run away.
            max_tokens=min(8192, 200 * num_cards + 512),
            system=_build_system_prompt(num_cards, language),
            tools=[_FLASHCARD_TOOL],
            tool_choice={"type": "tool", "name": FLASHCARD_TOOL_NAME},
            messages=[{"role": "user", "content": f"Study material:\n\n{material}"}],
        )
    except Exception as exc:
        raise FlashcardGenerationError(f"Claude flashcard request failed: {exc}") from exc

    return _parse_flashcards(_extract_tool_input(response))
