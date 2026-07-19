"""Flashcard — a generated front/back card over one Subject's material, scheduled with
the SM-2 spaced-repetition algorithm (see `sm2.py`).

A `Flashcard` belongs to exactly one `Subject`, same as `Quiz`. `owner_id` mirrors
`Subject.owner_id` — the same defense-in-depth tenant-scoping discipline used across
this codebase, enforced again here rather than relied on transitively through the FK.

The `Flashcard` row carries the CONTENT (front/back) **plus its OWNER's own inline SM-2
state** — the creator (a teacher, on a shared org subject) reviewing their own cards
keeps using these columns exactly as before org sharing existed. A NON-owner reviewer (a
student reviewing a teacher's shared org card) never touches this inline state; their
independent schedule lives in a separate `FlashcardReviewState` row (below), so two
students — and the owner — each keep a private schedule over the same shared card.

Plain FK columns, no ORM `relationship()`/cascade — consistent with the rest of the
codebase. `service.delete_flashcard` deletes a card's `FlashcardReviewState` rows (all
reviewers') before the card itself, the same flush-before-parent-delete FK ordering the
rest of this codebase follows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

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
    # difficulty" starting ease, so it appears in the very first due-cards review. This
    # is the OWNER's own schedule; a non-owner reviewer's lives in FlashcardReviewState.
    repetitions: int = Field(default=0)
    ease_factor: float = Field(default=DEFAULT_EASE_FACTOR)
    interval_days: int = Field(default=0)
    due_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    last_reviewed_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FlashcardReviewState(SQLModel, table=True):
    """A NON-owner reviewer's private SM-2 schedule for a shared flashcard.

    When a student reviews a teacher's org-shared card, their spaced-repetition
    schedule can't live on the `Flashcard` row (that's the teacher's own), and it must
    be isolated from every other student's — so each (card, reviewer) pair gets exactly
    one row here. `owner_id` is the **reviewer's** user id (NOT the card's owner). The
    card's own owner never gets a row here — they use the `Flashcard` inline columns.

    This model needs NO migration of existing flashcard data: personal/owner review
    still writes the inline `Flashcard` columns, entirely unchanged; this table only
    ever holds a non-owner's schedule, of which there were none before org sharing.
    """

    __tablename__ = "flashcard_review_states"
    __table_args__ = (
        # One schedule per reviewer per card — the upsert in service.review_flashcard
        # relies on this to never create a second row for the same (card, reviewer).
        UniqueConstraint("flashcard_id", "owner_id", name="uq_flashcard_review_state_card_owner"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    flashcard_id: uuid.UUID = Field(foreign_key="flashcards.id", index=True)
    # The REVIEWER's user id (not the card owner's) — indexed because due-card queries
    # filter a caller's own review-state rows.
    owner_id: str = Field(index=True)

    # This reviewer's own SM-2 state — same columns/semantics as Flashcard's inline
    # state, but private to this reviewer. Defaults match a brand-new card (due now).
    repetitions: int = Field(default=0)
    ease_factor: float = Field(default=DEFAULT_EASE_FACTOR)
    interval_days: int = Field(default=0)
    due_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    last_reviewed_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
