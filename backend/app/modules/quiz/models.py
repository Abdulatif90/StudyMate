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
from sqlmodel import Field, SQLModel


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
