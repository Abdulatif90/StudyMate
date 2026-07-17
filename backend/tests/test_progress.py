"""Tests for the progress module — router + service, against an in-memory SQLite DB.
No Claude/Cohere/R2/Inngest anywhere in this module (it's pure DB aggregation), so
every test here seeds data directly via the DB session and drives the real HTTP routes
— no mocking needed at all, unlike every other module's test file.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.main import app
from app.modules.documents.models import Document, DocumentStatus
from app.modules.flashcards.models import Flashcard
from app.modules.progress.service import MATURE_INTERVAL_DAYS_THRESHOLD
from app.modules.quiz.models import Quiz
from app.modules.subjects.models import Subject

_TEST_USER = "user_test_123"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)

# Relative to real wall-clock time, not a fixed date — the router (unlike
# flashcards_service.list_due_flashcards) has no client-suppliable `now` override (an
# HTTP caller shouldn't get to pick "now" for a due-count), so "due" here is computed
# against the real current time and the fixture must be relative to it too.
_PAST = datetime.now(UTC) - timedelta(days=1)
_FUTURE = datetime.now(UTC) + timedelta(days=1)


def _get_test_session():
    with Session(_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _isolated_db():
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    yield
    del app.dependency_overrides[get_session]
    del app.dependency_overrides[get_current_user_id]
    SQLModel.metadata.drop_all(_engine)


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _make_subject(owner_id: str, name: str = "Biology") -> uuid.UUID:
    with Session(_engine) as session:
        subject = Subject(owner_id=owner_id, name=name)
        session.add(subject)
        session.commit()
        session.refresh(subject)
        return subject.id


def _make_documents(owner_id: str, subject_id: uuid.UUID, statuses: list[DocumentStatus]) -> None:
    with Session(_engine) as session:
        for i, status in enumerate(statuses):
            session.add(
                Document(
                    subject_id=subject_id,
                    owner_id=owner_id,
                    filename=f"doc{i}.txt",
                    content_type="text/plain",
                    status=status,
                )
            )
        session.commit()


def _make_flashcard(
    owner_id: str,
    subject_id: uuid.UUID,
    *,
    repetitions: int,
    interval_days: int,
    due_at: datetime,
    last_reviewed_at: datetime | None,
) -> None:
    with Session(_engine) as session:
        session.add(
            Flashcard(
                subject_id=subject_id,
                owner_id=owner_id,
                front="front",
                back="back",
                repetitions=repetitions,
                interval_days=interval_days,
                due_at=due_at,
                last_reviewed_at=last_reviewed_at,
            )
        )
        session.commit()


def _make_quizzes(owner_id: str, subject_id: uuid.UUID, count: int) -> None:
    with Session(_engine) as session:
        for _ in range(count):
            session.add(Quiz(subject_id=subject_id, owner_id=owner_id))
        session.commit()


def _seed_known_dataset(owner_id: str, subject_id: uuid.UUID) -> None:
    """A fixed, hand-computed mix — see the module docstring's bucket math:
    documents: 2 ready, 1 pending, 1 failed (total 4).
    flashcards (5 total, due=2, new=2, learning=2, mature=1):
      A: new, due       (repetitions=0, never reviewed, due_at in the past)
      B: new, not due   (repetitions=0, never reviewed, due_at in the future)
      C: learning, not due (repetitions=1, interval=5, reviewed before, due in future)
      D: learning, due  (repetitions=0 but PREVIOUSLY reviewed — a lapsed/relapsed
                          card, not "new" again — due_at in the past)
      E: mature, not due (interval >= MATURE_INTERVAL_DAYS_THRESHOLD)
    quizzes: 2 generated.
    """
    _make_documents(
        owner_id,
        subject_id,
        [
            DocumentStatus.READY,
            DocumentStatus.READY,
            DocumentStatus.PENDING,
            DocumentStatus.FAILED,
        ],
    )
    _make_flashcard(
        owner_id, subject_id, repetitions=0, interval_days=0, due_at=_PAST, last_reviewed_at=None
    )  # A
    _make_flashcard(
        owner_id, subject_id, repetitions=0, interval_days=0, due_at=_FUTURE, last_reviewed_at=None
    )  # B
    _make_flashcard(
        owner_id, subject_id, repetitions=1, interval_days=5, due_at=_FUTURE, last_reviewed_at=_PAST
    )  # C
    _make_flashcard(
        owner_id, subject_id, repetitions=0, interval_days=1, due_at=_PAST, last_reviewed_at=_PAST
    )  # D
    _make_flashcard(
        owner_id,
        subject_id,
        repetitions=4,
        interval_days=MATURE_INTERVAL_DAYS_THRESHOLD + 5,
        due_at=_FUTURE,
        last_reviewed_at=_PAST,
    )  # E
    _make_quizzes(owner_id, subject_id, 2)


# --- Per-subject (GET /subjects/{subject_id}/progress) ----------------------


def test_subject_progress_computes_every_bucket_correctly():
    subject_id = _make_subject(_TEST_USER)
    _seed_known_dataset(_TEST_USER, subject_id)

    response = client.get(f"/subjects/{subject_id}/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["subject_id"] == str(subject_id)
    assert "owner_id" not in body

    assert body["documents"] == {"total": 4, "ready": 2, "pending": 1, "failed": 1}
    assert body["flashcards"] == {"total": 5, "due": 2, "new": 2, "learning": 2, "mature": 1}
    assert body["quiz_count"] == 2


def test_subject_progress_is_zeroed_for_a_subject_with_no_data():
    subject_id = _make_subject(_TEST_USER)

    response = client.get(f"/subjects/{subject_id}/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == {"total": 0, "ready": 0, "pending": 0, "failed": 0}
    assert body["flashcards"] == {"total": 0, "due": 0, "new": 0, "learning": 0, "mature": 0}
    assert body["quiz_count"] == 0


def test_subject_progress_due_count_is_deterministic_with_a_pinned_now():
    """Service-level (not HTTP): get_subject_progress accepts an overridable `now`,
    same as flashcards_service.list_due_flashcards, so "due" is computable against a
    fixed clock instead of racing wall time — this pins that contract directly rather
    than relying on the HTTP-level tests' real-time-relative fixture dates."""
    from app.modules.progress import service as progress_service

    subject_id = _make_subject(_TEST_USER)
    pinned_now = datetime(2026, 6, 1, tzinfo=UTC)
    _make_flashcard(
        _TEST_USER,
        subject_id,
        repetitions=0,
        interval_days=0,
        due_at=pinned_now - timedelta(days=1),  # due relative to pinned_now
        last_reviewed_at=None,
    )
    _make_flashcard(
        _TEST_USER,
        subject_id,
        repetitions=0,
        interval_days=0,
        due_at=pinned_now + timedelta(days=1),  # not due relative to pinned_now
        last_reviewed_at=None,
    )

    with Session(_engine) as session:
        result = progress_service.get_subject_progress(
            session, _TEST_USER, subject_id, now=pinned_now
        )

    assert result.flashcards.total == 2
    assert result.flashcards.due == 1


def test_subject_progress_excludes_a_sibling_subjects_data():
    subject_id = _make_subject(_TEST_USER, name="Biology")
    sibling_id = _make_subject(_TEST_USER, name="Chemistry")
    _seed_known_dataset(_TEST_USER, subject_id)
    _seed_known_dataset(_TEST_USER, sibling_id)  # same owner, different subject

    response = client.get(f"/subjects/{subject_id}/progress")

    body = response.json()
    # counts reflect ONE subject's data, not both subjects combined
    assert body["documents"]["total"] == 4
    assert body["flashcards"]["total"] == 5
    assert body["quiz_count"] == 2


def test_subject_progress_returns_404_for_missing_subject():
    response = client.get(f"/subjects/{_MISSING_ID}/progress")
    assert response.status_code == 404


def test_subject_progress_returns_404_for_another_owners_subject():
    subject_id = _make_subject("someone_else")
    _seed_known_dataset("someone_else", subject_id)

    # _TEST_USER (the authenticated caller) doesn't own this subject
    response = client.get(f"/subjects/{subject_id}/progress")
    assert response.status_code == 404


# --- Overall (GET /progress) -------------------------------------------------


def test_overall_progress_sums_across_all_of_the_callers_subjects():
    subject_a = _make_subject(_TEST_USER, name="Biology")
    subject_b = _make_subject(_TEST_USER, name="Chemistry")
    _seed_known_dataset(_TEST_USER, subject_a)
    _seed_known_dataset(_TEST_USER, subject_b)

    response = client.get("/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["subject_count"] == 2
    # two subjects' worth of the known dataset, summed
    assert body["documents"] == {"total": 8, "ready": 4, "pending": 2, "failed": 2}
    assert body["flashcards"] == {"total": 10, "due": 4, "new": 4, "learning": 4, "mature": 2}
    assert body["quiz_count"] == 4


def test_overall_progress_is_zeroed_for_a_caller_with_no_subjects():
    response = client.get("/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["subject_count"] == 0
    assert body["documents"]["total"] == 0
    assert body["flashcards"]["total"] == 0
    assert body["quiz_count"] == 0


def test_overall_progress_excludes_another_owners_data_entirely():
    # the caller (_TEST_USER) has one subject with data...
    own_subject = _make_subject(_TEST_USER)
    _seed_known_dataset(_TEST_USER, own_subject)

    # ...and someone_else has their OWN subject with their OWN data
    other_subject = _make_subject("someone_else")
    _seed_known_dataset("someone_else", other_subject)

    response = client.get("/progress")

    body = response.json()
    # only _TEST_USER's single subject's worth of data — someone_else's identical
    # dataset must not be summed in, the classic place a cross-tenant count leaks
    assert body["subject_count"] == 1
    assert body["documents"]["total"] == 4
    assert body["flashcards"]["total"] == 5
    assert body["quiz_count"] == 2


def test_overall_progress_for_the_other_owner_sees_only_their_own_data():
    # flip perspective: confirm scoping holds in both directions, not just one
    own_subject = _make_subject(_TEST_USER)
    _seed_known_dataset(_TEST_USER, own_subject)
    other_subject = _make_subject("someone_else")
    _seed_known_dataset("someone_else", other_subject)

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.get("/progress")

    body = response.json()
    assert body["subject_count"] == 1
    assert body["documents"]["total"] == 4
    assert body["flashcards"]["total"] == 5
    assert body["quiz_count"] == 2
