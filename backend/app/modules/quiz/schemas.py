"""Request/response shapes for the quiz API. `owner_id` is deliberately absent from
every read shape — never exposed over HTTP (same rule as everywhere else).

Answer-key exposure — decision: this increment is quiz *generation* + review for the
student's own material (owner-scoped, single user), with no graded submission flow yet.
So the read shapes intentionally **reveal** `correct_index` and `explanation` — the
quiz is a self-study/review tool (answer, then check yourself), like a flashcard.
If/when a graded-submission flow is added, it must NOT reuse `QuizQuestionRead` for the
"take the quiz" step: add a separate answer-hidden shape (question + options only) and
reveal `correct_index`/`explanation` only in the post-submission result. Documented here
so this choice is deliberate, not an accidental answer-key leak.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.language import DEFAULT_LANGUAGE


class QuizGenerateRequest(BaseModel):
    num_questions: int = Field(default=5, ge=1, le=20)
    title: str | None = Field(default=None, max_length=200)
    # A code from app.shared.language.SUPPORTED_LANGUAGES; unknown codes fall back to
    # English in language_name rather than rejecting the request.
    language: str = Field(default=DEFAULT_LANGUAGE)


class QuizQuestionRead(BaseModel):
    id: uuid.UUID
    question: str
    options: list[str]
    correct_index: int
    explanation: str | None
    order: int


class QuizRead(BaseModel):
    """List/summary shape — no questions (the list endpoint doesn't load them)."""

    id: uuid.UUID
    subject_id: uuid.UUID
    title: str | None
    created_at: datetime


class QuizWithQuestions(QuizRead):
    questions: list[QuizQuestionRead]


class QuizAttemptRequest(BaseModel):
    """A student's submitted answers for one quiz attempt: a mapping of question id →
    chosen option index. The server grades these against each question's `correct_index`
    (`service.grade_and_record_attempt`) — a client-computed score is NEVER accepted, so
    no score field exists here. Unknown question ids are ignored, and a missing or
    out-of-range index simply counts as wrong (graded leniently, never a 500)."""

    answers: dict[uuid.UUID, int] = Field(default_factory=dict)


class QuizAttemptResult(BaseModel):
    """The server-authoritative grade for one attempt. `total` is the number of questions
    in the quiz; `correct` is how many the student got right."""

    correct: int
    total: int
