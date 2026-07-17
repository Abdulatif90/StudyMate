"""Business logic for flashcards. Every function takes `owner_id` and filters by it —
same tenant-scoping discipline as the rest of this codebase. Generating/listing
operations are subject-scoped (confirm subject ownership first, reusing
`documents.service.require_owned_subject` — a flashcard can't be more accessible than
its subject); reviewing/deleting a single card only need `owner_id` + the card's own id
(same owner-scoped-by-id-alone pattern as `documents.service.get_document_by_id`), since
neither of those endpoints carries `subject_id` in its URL.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.modules.documents.service import require_owned_subject, sample_subject_chunk_texts
from app.modules.flashcards.generation import generate_flashcard_set
from app.modules.flashcards.models import Flashcard
from app.modules.flashcards.sm2 import ReviewState
from app.modules.flashcards.sm2 import review as sm2_review

# How many chunk excerpts to sample from the subject as material for one generation
# call — bounded so the generation prompt (and its cost/latency) stays predictable
# regardless of corpus size. Same reasoning/value as quiz.service.QUIZ_CHUNK_SAMPLE.
FLASHCARD_CHUNK_SAMPLE = 30


class NoFlashcardMaterialError(Exception):
    """Raised when a subject has no chunks to generate flashcards from (nothing
    uploaded yet, or nothing has finished processing) — a client-actionable condition,
    distinct from an upstream model failure."""


class InvalidGradeError(Exception):
    """Raised when a review grade is outside SM-2's 0-5 scale. The HTTP boundary
    (`ReviewRequest.grade`'s Pydantic `ge=0, le=5`) already rejects this before a
    request reaches here — this is defense-in-depth for any direct (non-HTTP) caller,
    so a corrupted grade can never reach `sm2.review` and silently corrupt a schedule.
    """


def generate_flashcards(
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    num_cards: int,
) -> list[Flashcard]:
    """Generate and persist flashcards for `subject_id`: verify ownership, sample the
    subject's material, generate via Claude tool-use, and store the `Flashcard` rows.

    Raises `SubjectNotFoundError` (unowned/missing subject), `NoFlashcardMaterialError`
    (no chunks to draw on), or `FlashcardGenerationError` (Claude failed / returned
    malformed cards) — all translated to HTTP status by the router. Nothing is
    persisted unless generation fully succeeds (rows are only built after the cards
    come back from Claude).
    """
    excerpts = sample_subject_chunk_texts(
        session, owner_id, subject_id, limit=FLASHCARD_CHUNK_SAMPLE
    )  # raises SubjectNotFoundError if unowned/missing
    if not excerpts:
        raise NoFlashcardMaterialError(subject_id)

    cards = generate_flashcard_set(excerpts, num_cards)

    # New cards start due immediately (due_at = now, repetitions/interval already
    # default to 0 and ease to DEFAULT_EASE_FACTOR on the model) so they show up in the
    # very first due-cards review rather than waiting out a phantom interval.
    now = datetime.now(UTC)
    flashcards = [
        Flashcard(
            subject_id=subject_id, owner_id=owner_id, front=card.front, back=card.back, due_at=now
        )
        for card in cards
    ]
    session.add_all(flashcards)
    session.commit()
    for flashcard in flashcards:
        session.refresh(flashcard)
    logging.getLogger(__name__).info(
        "Generated %d flashcards for subject %s", len(flashcards), subject_id
    )
    return flashcards


def list_flashcards(session: Session, owner_id: str, subject_id: uuid.UUID) -> list[Flashcard]:
    require_owned_subject(session, owner_id, subject_id)
    return list(
        session.exec(
            select(Flashcard)
            .where(Flashcard.subject_id == subject_id, Flashcard.owner_id == owner_id)
            .order_by(Flashcard.created_at)
        )
    )


def list_due_flashcards(
    session: Session, owner_id: str, subject_id: uuid.UUID, now: datetime | None = None
) -> list[Flashcard]:
    """Cards due for review at `now` (defaults to the real current time) — `now` is
    overridable so tests/live-verification can pin the clock instead of racing wall
    time, same reasoning as `sm2.review`'s own `now` parameter."""
    require_owned_subject(session, owner_id, subject_id)
    cutoff = now if now is not None else datetime.now(UTC)
    return list(
        session.exec(
            select(Flashcard)
            .where(
                Flashcard.subject_id == subject_id,
                Flashcard.owner_id == owner_id,
                Flashcard.due_at <= cutoff,
            )
            .order_by(Flashcard.due_at)
        )
    )


def get_flashcard(session: Session, owner_id: str, flashcard_id: uuid.UUID) -> Flashcard | None:
    """Owner-scoped lookup by id alone — review/delete don't carry `subject_id` in
    their URL (a card's id is already unique and unguessable), same pattern as
    `documents.service.get_document_by_id`."""
    return session.exec(
        select(Flashcard).where(Flashcard.id == flashcard_id, Flashcard.owner_id == owner_id)
    ).first()


def review_flashcard(
    session: Session,
    owner_id: str,
    flashcard_id: uuid.UUID,
    grade: int,
    now: datetime | None = None,
) -> Flashcard | None:
    """Grade one review of a flashcard (SM-2 `grade` 0-5) and persist its next
    schedule. Returns the updated card, or `None` if it doesn't exist / isn't owned by
    `owner_id` (router -> 404).

    Raises `InvalidGradeError` for a grade outside 0-5 (see its docstring — defense in
    depth, the HTTP schema already rejects this).
    """
    if not 0 <= grade <= 5:
        raise InvalidGradeError(f"grade must be between 0 and 5, got {grade}")

    flashcard = get_flashcard(session, owner_id, flashcard_id)
    if flashcard is None:
        return None

    review_time = now if now is not None else datetime.now(UTC)
    result = sm2_review(
        grade,
        ReviewState(
            repetitions=flashcard.repetitions,
            ease_factor=flashcard.ease_factor,
            interval_days=flashcard.interval_days,
        ),
        review_time,
    )

    flashcard.repetitions = result.repetitions
    flashcard.ease_factor = result.ease_factor
    flashcard.interval_days = result.interval_days
    flashcard.due_at = result.due_at
    flashcard.last_reviewed_at = review_time

    session.add(flashcard)
    session.commit()
    session.refresh(flashcard)
    return flashcard


def delete_flashcard(session: Session, owner_id: str, flashcard_id: uuid.UUID) -> bool:
    """Delete a flashcard. Returns `False` (router -> 404) when it doesn't exist or
    isn't owned by `owner_id`. No child rows to order around (unlike Quiz/QuizQuestion)
    — a plain single-row delete, no flush-before-parent dance needed here."""
    flashcard = get_flashcard(session, owner_id, flashcard_id)
    if flashcard is None:
        return False
    session.delete(flashcard)
    session.commit()
    return True
