"""Claude quiz generation via **tool-use structured output** (DECISIONS.md #5): quiz
JSON comes back as a validated tool call, never `json.loads` on free-text prose.

Claude is given a single `record_quiz` tool with a strict `input_schema` and forced to
call it (`tool_choice`), so the response is a `tool_use` block whose `.input` is a dict
the API already shaped to the schema. We still validate it defensively here (Claude can
satisfy the JSON-schema shape yet hallucinate an out-of-range `correct_index`), and any
violation — like any API/network failure or a response that somehow isn't a tool call —
becomes a `QuizGenerationError`.

Same Anthropic SDK / error-handling family as `ask/llm.py` and
`documents/summarization.py`: missing `ANTHROPIC_API_KEY` is a deployment mistake, so it
raises a bare `RuntimeError` at the point of use (like `db.py`/`embedding.py`); a
per-request failure is wrapped so the caller (`service.generate_quiz`) can surface a
clean error instead of crashing. Multilingual: the prompt tells Claude to write in the
same language as the source material (same approach as summary/ask).
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from app.core.config import get_settings

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# The tool Claude is forced to call. Its input_schema is the contract: a `questions`
# array, each with a question, its options, the index of the correct one, and a short
# explanation. `additionalProperties: false` + `required` keep Claude from drifting the
# shape. This is the structured-output boundary — nothing downstream parses prose.
QUIZ_TOOL_NAME = "record_quiz"
_QUIZ_TOOL = {
    "name": QUIZ_TOOL_NAME,
    "description": (
        "Record the generated multiple-choice quiz questions. Call this exactly once "
        "with all the questions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The question stem.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Answer choices — at least 2, exactly one correct.",
                        },
                        "correct_index": {
                            "type": "integer",
                            "description": "0-based index into `options` of the correct choice.",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Brief explanation of why the correct choice is right.",
                        },
                    },
                    "required": ["question", "options", "correct_index", "explanation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
}


class QuizGenerationError(Exception):
    """Raised when Claude can't produce a well-formed quiz."""


@dataclass(frozen=True)
class GeneratedQuestion:
    """One validated MCQ from the tool response — shape already checked (options is a
    non-empty list of strings, correct_index is within range), ready for the service to
    persist without re-validating."""

    question: str
    options: list[str]
    correct_index: int
    explanation: str


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_system_prompt(num_questions: int) -> str:
    return (
        "You are StudyMate, an AI study assistant. Using ONLY the study material "
        f"excerpts provided, write {num_questions} multiple-choice quiz questions that "
        "test understanding of the material — not trivia about its wording. Each "
        "question has exactly one correct answer and 3-4 plausible options. Write the "
        "questions, options, and explanations in the same language as the source "
        "material. Do not use outside knowledge. Return the questions by calling the "
        f"`{QUIZ_TOOL_NAME}` tool — do not write any prose."
    )


def _extract_tool_input(response: anthropic.types.Message) -> dict:
    """Pull the forced tool call's `.input` (a dict) out of the response, or raise
    `QuizGenerationError` if — despite `tool_choice` forcing it — no tool_use block is
    present (e.g. the model hit max_tokens mid-call and returned a partial/other block).
    """
    for block in response.content:
        if block.type == "tool_use" and block.name == QUIZ_TOOL_NAME:
            return block.input
    raise QuizGenerationError("Claude did not return a quiz tool call")


def _parse_questions(tool_input: dict) -> list[GeneratedQuestion]:
    """Validate the tool input into `GeneratedQuestion`s. Defensive even though the API
    shaped it to the schema: `correct_index` in particular can be schema-valid (an
    integer) yet out of range, which would silently break grading later."""
    raw_questions = tool_input.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise QuizGenerationError("Quiz tool call contained no questions")

    questions: list[GeneratedQuestion] = []
    for raw in raw_questions:
        question = raw.get("question")
        options = raw.get("options")
        correct_index = raw.get("correct_index")
        explanation = raw.get("explanation")

        if not isinstance(question, str) or not question.strip():
            raise QuizGenerationError("A question was missing its text")
        if not isinstance(options, list) or len(options) < 2:
            raise QuizGenerationError("A question had fewer than 2 options")
        if not all(isinstance(option, str) and option.strip() for option in options):
            raise QuizGenerationError("A question had a non-string or empty option")
        if not isinstance(correct_index, int) or isinstance(correct_index, bool):
            raise QuizGenerationError("A question had a non-integer correct_index")
        if not 0 <= correct_index < len(options):
            raise QuizGenerationError(
                f"correct_index {correct_index} is out of range for {len(options)} options"
            )
        if not isinstance(explanation, str):
            raise QuizGenerationError("A question had a non-string explanation")

        questions.append(
            GeneratedQuestion(
                question=question,
                options=options,
                correct_index=correct_index,
                explanation=explanation,
            )
        )
    return questions


def generate_quiz_questions(excerpts: list[str], num_questions: int) -> list[GeneratedQuestion]:
    """Generate `num_questions` MCQs from `excerpts` (a subject's retrieved chunk texts)
    via Claude tool-use. Returns validated `GeneratedQuestion`s. Raises
    `QuizGenerationError` on any API failure or malformed/empty response.
    """
    if not excerpts:
        raise QuizGenerationError("No material to generate a quiz from")

    client = _get_client()
    material = "\n\n---\n\n".join(excerpts)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            # Budget scales with question count; each MCQ + explanation is a few hundred
            # tokens. Bounded so a huge num_questions can't run away.
            max_tokens=min(8192, 350 * num_questions + 512),
            system=_build_system_prompt(num_questions),
            tools=[_QUIZ_TOOL],
            tool_choice={"type": "tool", "name": QUIZ_TOOL_NAME},
            messages=[{"role": "user", "content": f"Study material:\n\n{material}"}],
        )
    except Exception as exc:
        raise QuizGenerationError(f"Claude quiz request failed: {exc}") from exc

    return _parse_questions(_extract_tool_input(response))
