"""Business logic for progress — read-only aggregation over a caller's EXISTING data
(documents, flashcards, quizzes). No models of its own, same shape as `ask` (which also
has no models of its own): every function here is a query over tables other modules
own, always filtered by `owner_id` — directly, not via a join through `Subject` —
since `Document`/`Flashcard`/`Quiz` all already carry a denormalized `owner_id` column
(the same defense-in-depth tenant-scoping used everywhere else in this codebase), which
makes "only this caller's data" a plain equality filter on each table, no join needed.

Quiz *attempts/scores* aren't tracked anywhere yet — quiz grading is entirely
client-side (see `quiz/schemas.py`'s answer-key decision: `correct_index` is revealed
in the read shape and compared in the browser, nothing is ever submitted back). So
`quiz_count` below is how many quizzes were *generated*, not a performance history.
Making quiz results trackable would need a new `QuizAttempt` model (quiz_id FK,
owner_id, score, total, created_at) + a submission endpoint + its own migration/tests/
tenant-scoping — deliberately out of scope for this increment (a focused, read-only
aggregation of what already exists); noted as a follow-up in `docs/PROGRESS.md`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, func, select

from app.modules.documents.models import Document, DocumentStatus
from app.modules.documents.service import require_owned_subject
from app.modules.flashcards.models import Flashcard
from app.modules.progress.schemas import (
    DocumentStatusCounts,
    FlashcardProgress,
    OverallProgress,
    SubjectProgress,
)
from app.modules.quiz.models import Quiz
from app.modules.subjects.models import Subject

# A flashcard's `interval_days` at or beyond this is "mature" (well-learned, reviewed
# infrequently) rather than "learning" (still being actively drilled). 21 days matches
# Anki's own young/mature cutoff — a familiar, documented reference point rather than an
# arbitrary number invented for this codebase.
MATURE_INTERVAL_DAYS_THRESHOLD = 21


def _document_status_counts(
    session: Session, owner_id: str, subject_id: uuid.UUID | None
) -> DocumentStatusCounts:
    """One GROUP BY query, not three separate COUNTs — `status` only has three possible
    values, so a single grouped aggregate is both fewer round trips and the more
    natural SQL shape for "counts by category" than three individually-filtered ones.
    """
    filters = [Document.owner_id == owner_id]
    if subject_id is not None:
        filters.append(Document.subject_id == subject_id)

    rows = session.exec(
        select(Document.status, func.count()).where(*filters).group_by(Document.status)
    ).all()
    counts = dict(rows)

    ready = counts.get(DocumentStatus.READY, 0)
    pending = counts.get(DocumentStatus.PENDING, 0)
    failed = counts.get(DocumentStatus.FAILED, 0)
    return DocumentStatusCounts(
        total=ready + pending + failed, ready=ready, pending=pending, failed=failed
    )


def _flashcard_progress(
    session: Session, owner_id: str, subject_id: uuid.UUID | None, now: datetime | None
) -> FlashcardProgress:
    """4 scalar COUNTs, not "load every flashcard and count in Python" — each is a
    single indexed aggregate query (`due_at`/`owner_id`/`subject_id` are all indexed on
    `Flashcard`).

    Bucketing, and why `learning` is derived rather than queried directly: `new` (never
    reviewed at all — `repetitions == 0 AND last_reviewed_at IS NULL`) and `mature`
    (`interval_days >= MATURE_INTERVAL_DAYS_THRESHOLD`) are mutually exclusive by
    construction — a card only ever gets a non-zero `interval_days` via a review (see
    `flashcards.service.review_flashcard`), and a review always sets
    `last_reviewed_at`, so nothing in the `new` bucket can also be in `mature`. That
    makes `total - new - mature` an exact count of everything else — a genuinely
    "still being learned" card, *including* one that lapsed back to `repetitions == 0`
    (it keeps its `last_reviewed_at`, so it's correctly `learning`, not `new` again) —
    without a fourth query.

    `due` is a different, orthogonal dimension (a card can be new-and-due,
    learning-and-due, or mature-and-due at once), so it's its own independent COUNT,
    not part of the new/learning/mature partition.
    """
    cutoff = now if now is not None else datetime.now(UTC)
    filters = [Flashcard.owner_id == owner_id]
    if subject_id is not None:
        filters.append(Flashcard.subject_id == subject_id)

    total = session.exec(select(func.count()).select_from(Flashcard).where(*filters)).one()
    due = session.exec(
        select(func.count()).select_from(Flashcard).where(*filters, Flashcard.due_at <= cutoff)
    ).one()
    new = session.exec(
        select(func.count())
        .select_from(Flashcard)
        .where(*filters, Flashcard.repetitions == 0, Flashcard.last_reviewed_at.is_(None))
    ).one()
    mature = session.exec(
        select(func.count())
        .select_from(Flashcard)
        .where(*filters, Flashcard.interval_days >= MATURE_INTERVAL_DAYS_THRESHOLD)
    ).one()

    return FlashcardProgress(
        total=total, due=due, new=new, learning=total - new - mature, mature=mature
    )


def _quiz_count(session: Session, owner_id: str, subject_id: uuid.UUID | None) -> int:
    filters = [Quiz.owner_id == owner_id]
    if subject_id is not None:
        filters.append(Quiz.subject_id == subject_id)
    return session.exec(select(func.count()).select_from(Quiz).where(*filters)).one()


def get_subject_progress(
    session: Session, owner_id: str, subject_id: uuid.UUID, now: datetime | None = None
) -> SubjectProgress:
    """Progress rollup for one subject. Raises `SubjectNotFoundError`
    (`documents.service`) if `subject_id` doesn't exist or isn't owned by `owner_id` —
    a progress endpoint that revealed *counts* for a subject the caller can't otherwise
    see would itself be a tenant leak, so this is checked before any aggregate runs.
    """
    require_owned_subject(session, owner_id, subject_id)
    return SubjectProgress(
        subject_id=subject_id,
        documents=_document_status_counts(session, owner_id, subject_id),
        flashcards=_flashcard_progress(session, owner_id, subject_id, now),
        quiz_count=_quiz_count(session, owner_id, subject_id),
    )


def get_overall_progress(
    session: Session, owner_id: str, now: datetime | None = None
) -> OverallProgress:
    """Progress rollup across every subject `owner_id` owns. No `subject_id` filter on
    any of the aggregates — scoping is `owner_id` alone, which is already exactly "this
    caller's data and nothing else" since every aggregated table carries its own
    `owner_id` column directly (see this module's docstring).
    """
    subject_count = session.exec(
        select(func.count()).select_from(Subject).where(Subject.owner_id == owner_id)
    ).one()
    return OverallProgress(
        subject_count=subject_count,
        documents=_document_status_counts(session, owner_id, subject_id=None),
        flashcards=_flashcard_progress(session, owner_id, subject_id=None, now=now),
        quiz_count=_quiz_count(session, owner_id, subject_id=None),
    )
