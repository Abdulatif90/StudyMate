"""Flashcard — a generated front/back card over one Subject's material, scheduled with
the SM-2 spaced-repetition algorithm (see `sm2.py`).

A `Flashcard` belongs to exactly one `Subject`, same as `Quiz`. `owner_id` mirrors
`Subject.owner_id` — the same defense-in-depth tenant-scoping discipline used across
this codebase, enforced again here rather than relied on transitively through the FK.

Plain FK column, no ORM `relationship()`/cascade — consistent with the rest of the
codebase. This table has no child rows of its own (unlike Quiz/QuizQuestion), so it
doesn't need the flush-before-parent-delete dance that FK-ordering bugs have surfaced
four times before (Document/DocumentChunk, `delete_conversation`, `delete_document`,
`delete_quiz`) — but `service.delete_flashcard` is still a plain single-row delete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.modules.flashcards.sm2 import DEFAULT_EASE_FACTOR


class Flashcard(SQLModel, table=True):
    __tablename__ = "flashcards"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    owner_id: str = Field(index=True)
    front: str
    back: str

    # SM-2 scheduling state (see sm2.py) — a new card starts due immediately (due_at =
    # its creation time), with zero repetitions and the SM-2-standard "average
    # difficulty" starting ease, so it appears in the very first due-cards review.
    repetitions: int = Field(default=0)
    ease_factor: float = Field(default=DEFAULT_EASE_FACTOR)
    interval_days: int = Field(default=0)
    due_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    last_reviewed_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
