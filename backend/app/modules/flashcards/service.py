"""Business logic for flashcards.

Two access shapes, matching the org-sharing model the rest of the codebase already uses
(single source of truth: `subjects.service`'s `can_read_subject` / `can_write_subject`
predicates and their `require_*` wrappers):

- **Read / generate** (generate, list, due) are subject-READABILITY-scoped: the owner of
  a private subject, or any member whose active org owns the subject, may generate/read.
  A member generating over a teacher's org subject gets cards **owned by the caller**
  (per-student ownership, like conversations) — the shared thing is the source material,
  not the derived cards.
- **Review / delete** address a single card by its id alone (no `subject_id` in the URL).
  Reviewing is readability-scoped (a non-owner reviewer keeps a PRIVATE SM-2 schedule in
  a `FlashcardReviewState` row, never touching the owner's inline columns); deleting is
  OWNER-only (a student can't delete a teacher's shared card).

The caller's *effective* schedule (returned as `ScheduledFlashcard`) is the inline
`Flashcard` columns for their own cards, and their own `FlashcardReviewState` row (or a
brand-new default) for a subject owner's shared card — so two students, and the owner,
each keep an independent schedule over the same card.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, delete, select

from app.core.org import OrgContext
from app.modules.billing.models import GenerationKind
from app.modules.billing.service import ensure_can_generate, record_generation
from app.modules.documents.service import (
    require_owned_subject,
    sample_subject_chunk_texts_for_reader,
)
from app.modules.flashcards.generation import generate_flashcard_set
from app.modules.flashcards.models import Flashcard, FlashcardReviewState
from app.modules.flashcards.sm2 import DEFAULT_EASE_FACTOR, ReviewState
from app.modules.flashcards.sm2 import review as sm2_review
from app.modules.subjects.models import Subject
from app.modules.subjects.service import get_readable_subject, require_readable_subject
from app.shared.language import DEFAULT_LANGUAGE

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


@dataclass(frozen=True)
class ScheduledFlashcard:
    """A flashcard's content paired with the CALLER's effective SM-2 schedule.

    `id` is always the CARD's id (review/delete address the card by id, so this must
    stay stable regardless of whose schedule is shown). For the caller's own cards the
    schedule fields are the inline `Flashcard` columns; for a subject owner's shared card
    they come from the caller's `FlashcardReviewState`, or a brand-new default (due at the
    card's creation → due immediately, repetitions 0, default ease) when the caller has
    not reviewed it yet.
    """

    id: uuid.UUID
    subject_id: uuid.UUID
    front: str
    back: str
    repetitions: int
    ease_factor: float
    interval_days: int
    due_at: datetime
    last_reviewed_at: datetime | None
    created_at: datetime


def _to_scheduled(
    card: Flashcard, caller_id: str, state: FlashcardReviewState | None
) -> ScheduledFlashcard:
    """Pair `card`'s content with `caller_id`'s effective schedule (see
    `ScheduledFlashcard`). `state` is the caller's review-state row for the card, or None
    (either the card is the caller's own — inline columns — or they've not reviewed a
    shared card yet — brand-new default)."""
    if card.owner_id == caller_id:
        source: Flashcard | FlashcardReviewState = card
    elif state is not None:
        source = state
    else:
        # Non-owner reader who has never reviewed this shared card: a brand-new default
        # schedule. `due_at = card.created_at` is deterministically in the past, so the
        # card is due immediately for this reviewer — the same "new cards are due now"
        # semantics the owner's own freshly generated cards get.
        return ScheduledFlashcard(
            id=card.id,
            subject_id=card.subject_id,
            front=card.front,
            back=card.back,
            repetitions=0,
            ease_factor=DEFAULT_EASE_FACTOR,
            interval_days=0,
            due_at=card.created_at,
            last_reviewed_at=None,
            created_at=card.created_at,
        )
    return ScheduledFlashcard(
        id=card.id,
        subject_id=card.subject_id,
        front=card.front,
        back=card.back,
        repetitions=source.repetitions,
        ease_factor=source.ease_factor,
        interval_days=source.interval_days,
        due_at=source.due_at,
        last_reviewed_at=source.last_reviewed_at,
        created_at=card.created_at,
    )


def _reader_owner_filter(caller_id: str, subject: Subject):
    """The `Flashcard.owner_id` filter for what a reader sees on `subject`: always their
    OWN cards; PLUS, when they are not the subject owner, the subject OWNER's cards (the
    shared set). Deliberately never another student's private cards — only the owner's
    cards are shared."""
    own = Flashcard.owner_id == caller_id
    if subject.owner_id == caller_id:
        return own
    return own | (Flashcard.owner_id == subject.owner_id)


def _attach_schedules(
    session: Session, caller_id: str, cards: list[Flashcard]
) -> list[ScheduledFlashcard]:
    """Resolve each card to the caller's effective schedule — one query for all of the
    caller's review-state rows over the shared (non-own) cards in `cards`, rather than
    one per card."""
    shared_ids = [card.id for card in cards if card.owner_id != caller_id]
    states: dict[uuid.UUID, FlashcardReviewState] = {}
    if shared_ids:
        rows = session.exec(
            select(FlashcardReviewState).where(
                FlashcardReviewState.owner_id == caller_id,
                FlashcardReviewState.flashcard_id.in_(shared_ids),
            )
        )
        states = {row.flashcard_id: row for row in rows}
    return [_to_scheduled(card, caller_id, states.get(card.id)) for card in cards]


def _get_review_state(
    session: Session, caller_id: str, flashcard_id: uuid.UUID
) -> FlashcardReviewState | None:
    """The caller's own review-state row for a card, if any (the unique
    (flashcard_id, owner_id) constraint guarantees at most one)."""
    return session.exec(
        select(FlashcardReviewState).where(
            FlashcardReviewState.flashcard_id == flashcard_id,
            FlashcardReviewState.owner_id == caller_id,
        )
    ).first()


def _as_naive_utc(value: datetime) -> datetime:
    """Normalize a datetime to naive-UTC for comparison. The `due_at` columns are stored
    as timezone-naive (both on SQLite in tests and in the non-tz Postgres columns), while
    `datetime.now(UTC)` is tz-aware — comparing the two directly raises. This coerces an
    aware value to naive-UTC and passes a naive one through, so the due cutoff compares
    cleanly on either backend."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def generate_flashcards(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    num_cards: int,
    language: str = DEFAULT_LANGUAGE,
) -> list[Flashcard]:
    """Generate and persist flashcards for `subject_id`: verify the caller may READ the
    subject, sample its material, generate via Claude tool-use, and store the `Flashcard`
    rows **owned by the caller** (`owner_id = caller_id`) — so a member generating over a
    teacher's org subject gets their own private cards, exactly like conversations.

    Raises `SubjectNotFoundError` (subject missing or not readable by the caller),
    `NoFlashcardMaterialError` (no chunks to draw on), or `FlashcardGenerationError`
    (Claude failed / returned malformed cards) — all translated to HTTP status by the
    router. Nothing is persisted unless generation fully succeeds (rows are only built
    after the cards come back from Claude).
    """
    excerpts = sample_subject_chunk_texts_for_reader(
        session, caller_id, org_ctx, subject_id, limit=FLASHCARD_CHUNK_SAMPLE
    )  # raises SubjectNotFoundError if the caller may not read the subject
    if not excerpts:
        raise NoFlashcardMaterialError(subject_id)

    # Daily-generation guard BEFORE the Claude call below, so a quota-rejected request
    # never spends a billable API call. Raises PlanLimitExceededError (-> 402, handled
    # app-wide in main.py). See billing.service for the check/record ordering contract.
    ensure_can_generate(session, caller_id, org_ctx=org_ctx)

    cards = generate_flashcard_set(excerpts, num_cards, language)

    # New cards start due immediately (due_at = now, repetitions/interval already
    # default to 0 and ease to DEFAULT_EASE_FACTOR on the model) so they show up in the
    # very first due-cards review rather than waiting out a phantom interval.
    now = datetime.now(UTC)
    flashcards = [
        Flashcard(
            subject_id=subject_id, owner_id=caller_id, front=card.front, back=card.back, due_at=now
        )
        for card in cards
    ]
    session.add_all(flashcards)
    # ONE generation event, regardless of how many cards it produced — this is exactly
    # why the counter is its own table rather than a COUNT of Flashcard rows (see
    # billing.models.GenerationUsage). Staged on the same session so the commit below
    # persists counter + cards atomically; only reached after generation succeeded.
    record_generation(session, caller_id, GenerationKind.FLASHCARD)
    session.commit()
    for flashcard in flashcards:
        session.refresh(flashcard)
    logging.getLogger(__name__).info(
        "Generated %d flashcards for subject %s", len(flashcards), subject_id
    )
    return flashcards


def list_flashcards(session: Session, owner_id: str, subject_id: uuid.UUID) -> list[Flashcard]:
    """Owner-scoped list of a subject's flashcards. KEPT owner-scoped (not readability-
    scoped): used by `subjects.service.delete_subject`'s cascade, which enumerates the
    subject OWNER's own cards. The READ path (a member browsing an org subject) uses
    `list_flashcards_for_reader` instead."""
    require_owned_subject(session, owner_id, subject_id)
    return list(
        session.exec(
            select(Flashcard)
            .where(Flashcard.subject_id == subject_id, Flashcard.owner_id == owner_id)
            .order_by(Flashcard.created_at)
        )
    )


def list_all_flashcards_for_subject(session: Session, subject_id: uuid.UUID) -> list[Flashcard]:
    """ALL of a subject's flashcards, EVERY owner, with NO ownership/access check —
    **cascade-only**, same spirit as `subjects.service._get_subject_by_id`. Never expose
    to a request path: used exclusively by `subjects.service.delete_subject` to enumerate
    every member's cards on a shared org subject (each then passed to the owner-scoped
    `delete_flashcard` with its own `owner_id`, which also clears that card's
    `FlashcardReviewState` rows for ALL reviewers), so the subject delete can't hit an FK
    violation from another member's cards or review-state rows."""
    return list(session.exec(select(Flashcard).where(Flashcard.subject_id == subject_id)))


def list_flashcards_for_reader(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> list[ScheduledFlashcard]:
    """A subject's flashcards for anyone who may READ it, each with the CALLER's
    effective schedule. Verifies readability first (`SubjectNotFoundError` → 404 if
    denied), then returns the caller's own cards PLUS — when the caller isn't the subject
    owner — the subject owner's cards (the shared set), never another student's."""
    subject = require_readable_subject(session, caller_id, org_ctx, subject_id)
    cards = list(
        session.exec(
            select(Flashcard)
            .where(Flashcard.subject_id == subject_id, _reader_owner_filter(caller_id, subject))
            .order_by(Flashcard.created_at)
        )
    )
    return _attach_schedules(session, caller_id, cards)


def list_due_flashcards_for_reader(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    now: datetime | None = None,
) -> list[ScheduledFlashcard]:
    """Cards due for review at `now` (defaults to the real current time) against the
    CALLER's EFFECTIVE schedule — a shared card's due date is the caller's own
    review-state (or the brand-new default), never the owner's inline `due_at`. `now` is
    overridable so tests/live-verification can pin the clock instead of racing wall time,
    same reasoning as `sm2.review`'s own `now` parameter.

    The cutoff is applied in Python (not SQL) because the effective `due_at` is
    per-caller and can come from three sources (own inline column, review-state row, or
    default), which a single SQL predicate over `Flashcard` can't express."""
    subject = require_readable_subject(session, caller_id, org_ctx, subject_id)
    cutoff = _as_naive_utc(now if now is not None else datetime.now(UTC))
    cards = list(
        session.exec(
            select(Flashcard).where(
                Flashcard.subject_id == subject_id, _reader_owner_filter(caller_id, subject)
            )
        )
    )
    due = [
        scheduled
        for scheduled in _attach_schedules(session, caller_id, cards)
        if _as_naive_utc(scheduled.due_at) <= cutoff
    ]
    due.sort(key=lambda scheduled: _as_naive_utc(scheduled.due_at))
    return due


def get_flashcard(session: Session, owner_id: str, flashcard_id: uuid.UUID) -> Flashcard | None:
    """Owner-scoped lookup by id alone — used by `delete_flashcard` (only a card's owner
    may delete it) and callers that specifically want owner scoping. Same pattern as
    `documents.service.get_document_by_id`."""
    return session.exec(
        select(Flashcard).where(Flashcard.id == flashcard_id, Flashcard.owner_id == owner_id)
    ).first()


def review_flashcard(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    flashcard_id: uuid.UUID,
    grade: int,
    now: datetime | None = None,
) -> ScheduledFlashcard | None:
    """Grade one review of a flashcard (SM-2 `grade` 0-5) and persist the CALLER's next
    schedule. Returns the card with the caller's effective schedule, or `None` (router →
    404) if the card doesn't exist or the caller may not read its subject.

    - Own card (`owner_id == caller_id`) → update the inline `Flashcard` columns
      (unchanged behavior).
    - A subject owner's shared card the caller may read → **upsert** the caller's
      `FlashcardReviewState` and advance THAT schedule, never touching the owner's inline
      columns. The (flashcard_id, owner_id) unique constraint keeps one row per (card,
      reviewer), so two students keep independent schedules over the same shared card.

    Raises `InvalidGradeError` for a grade outside 0-5 (see its docstring — defense in
    depth; the HTTP schema already rejects this).
    """
    if not 0 <= grade <= 5:
        raise InvalidGradeError(f"grade must be between 0 and 5, got {grade}")

    card = session.get(Flashcard, flashcard_id)
    if card is None:
        return None

    review_time = now if now is not None else datetime.now(UTC)

    if card.owner_id == caller_id:
        result = sm2_review(
            grade,
            ReviewState(
                repetitions=card.repetitions,
                ease_factor=card.ease_factor,
                interval_days=card.interval_days,
            ),
            review_time,
        )
        card.repetitions = result.repetitions
        card.ease_factor = result.ease_factor
        card.interval_days = result.interval_days
        card.due_at = result.due_at
        card.last_reviewed_at = review_time
        session.add(card)
        session.commit()
        session.refresh(card)
        return _to_scheduled(card, caller_id, None)

    # Non-owner reviewer: they may only review the SUBJECT OWNER's shared card (the same
    # set `_reader_owner_filter` exposes in listing) — never another student's private
    # card. So the subject must be readable AND the card must belong to the subject's
    # owner. Either miss → None (→ 404), same as a missing card, so a caller can't probe
    # for another student's card by id (their state stays owner_id-scoped; only source
    # material is shared).
    subject = get_readable_subject(session, caller_id, org_ctx, card.subject_id)
    if subject is None or card.owner_id != subject.owner_id:
        return None

    # Upsert the caller's private schedule — never the owner's inline columns.
    state = _get_review_state(session, caller_id, flashcard_id)
    if state is None:
        state = FlashcardReviewState(flashcard_id=flashcard_id, owner_id=caller_id)

    result = sm2_review(
        grade,
        ReviewState(
            repetitions=state.repetitions,
            ease_factor=state.ease_factor,
            interval_days=state.interval_days,
        ),
        review_time,
    )
    state.repetitions = result.repetitions
    state.ease_factor = result.ease_factor
    state.interval_days = result.interval_days
    state.due_at = result.due_at
    state.last_reviewed_at = review_time
    session.add(state)
    session.commit()
    session.refresh(state)
    return _to_scheduled(card, caller_id, state)


def delete_flashcard(
    session: Session, caller_id: str, flashcard_id: uuid.UUID, *, commit: bool = True
) -> bool:
    """Delete a flashcard. Returns `False` (router → 404) when it doesn't exist or isn't
    owned by `caller_id` — **only the card's OWNER may delete it**, so a student can't
    delete a teacher's shared card (they get the same 404 as a missing card).

    A card's `FlashcardReviewState` rows (every reviewer's private schedule over it) are
    deleted and flushed BEFORE the parent card — the same flush-before-parent-delete FK
    ordering the rest of this codebase follows (there's no ORM `relationship()`/cascade,
    so SQLAlchemy won't order the deletes for us, and deleting the card first would hit
    the `flashcard_id` FK).

    `commit=False` (used by `subjects.service.delete_subject`, cascading a whole
    subject's deletion in one transaction): flushes instead of committing, so the
    caller's own commit/rollback governs this delete too.
    """
    flashcard = get_flashcard(session, caller_id, flashcard_id)
    if flashcard is None:
        return False

    session.exec(
        delete(FlashcardReviewState).where(FlashcardReviewState.flashcard_id == flashcard_id)
    )
    session.flush()
    session.delete(flashcard)
    if commit:
        session.commit()
    else:
        session.flush()
    return True
