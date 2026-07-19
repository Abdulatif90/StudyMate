"""Quiz — a generated set of multiple-choice questions over one Subject's material.

A `Quiz` belongs to exactly one `Subject` (its questions are generated from that
subject's document chunks); each `QuizQuestion` is one MCQ within it. `owner_id`
mirrors `Subject.owner_id` on both tables — the same defense-in-depth tenant-scoping
discipline used across this codebase (`Document`, `Conversation`, ...), enforced again
here rather than relied on transitively through the FK.

Plain FK columns, no ORM `relationship()`/cascade — consistent with the rest of the
codebase. This means deletes are *not* automatically ordered: deleting a `Quiz` and its
`QuizQuestion` rows needs an explicit `session.flush()` between the child deletes and
the parent delete (see `service.delete_quiz`), the same flush-before-parent-delete rule
that FK-ordering bugs surfaced three times before (Document/DocumentChunk,
`delete_conversation`, `delete_document`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, UniqueConstraint


class Quiz(SQLModel, table=True):
    __tablename__ = "quizzes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    owner_id: str = Field(index=True)
    title: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QuizQuestion(SQLModel, table=True):
    __tablename__ = "quiz_questions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    quiz_id: uuid.UUID = Field(foreign_key="quizzes.id", index=True)
    owner_id: str = Field(index=True)
    question: str
    # The answer choices, in display order. JSON list, never NULL (always a real list,
    # at least two options — enforced by generation.py before persisting). Same
    # none_as_null-free NOT-NULL JSON pattern as `ConversationTurn.sources`.
    options: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # Index into `options` of the correct choice. Validated server-side to be within
    # range before persisting (see `service.generate_quiz`) — a hallucinated
    # out-of-range index would silently break any future grading flow.
    correct_index: int
    explanation: str | None = Field(default=None)
    # Position of this question within its quiz (0-based), so questions render in the
    # order Claude generated them rather than by row insertion order / PK.
    order: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QuizAttempt(SQLModel, table=True):
    """A single student's graded attempt at a quiz (Phase 5 increment 4a).

    The score is authoritative and computed **server-side** in `service.grade_and_record_attempt`
    against each `QuizQuestion.correct_index` — a client-reported score is never trusted.
    `correct`/`total` are the graded result; `total` is the number of questions in the quiz
    (any unanswered/invalid answer counts as wrong).

    **One row per (quiz, student)** — enforced by the DB `UniqueConstraint`, UPSERTED on
    each submit so the **latest attempt wins** (simplest, predictable; we deliberately do
    NOT keep a full attempt history this increment). `owner_id` is the STUDENT who took it.
    `subject_id` is denormalized (like `Quiz`) for tenant-scoping without a join.

    Plain FK columns, no ORM `relationship()`/cascade — consistent with the rest of the
    codebase. A future quiz-delete cascade must delete attempt rows before the quiz row,
    the same flush-before-parent-delete FK rule the other tables follow.
    """

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        # One attempt row per student per quiz — the upsert in
        # service.grade_and_record_attempt relies on this to never create a second row.
        UniqueConstraint("quiz_id", "owner_id", name="uq_quiz_attempt_quiz_owner"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    quiz_id: uuid.UUID = Field(foreign_key="quizzes.id", index=True)
    # Denormalized subject scope (mirrors Quiz.subject_id), FK for referential integrity.
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    # The STUDENT who took the quiz (Clerk user id) — the owner scope. Indexed.
    owner_id: str = Field(index=True)
    correct: int
    total: int
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
