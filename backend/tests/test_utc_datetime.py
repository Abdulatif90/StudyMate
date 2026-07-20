"""The API's JSON output must carry an explicit UTC marker on every datetime.

Regression guard for the tz-drift bug: models store `datetime.now(UTC)` but the DB
columns are `TIMESTAMP WITHOUT TIME ZONE`, so values round-trip NAIVE. Serialized without
a timezone marker, the frontend's `new Date(str)` reads them as *local* time and shifts
every timestamp by the viewer's offset (fresh assignment shows "Overdue", wrong quiz
times). `app.shared.datetime.UtcDatetime` assumes a naive stored value is UTC and emits an
explicit offset, so these tests assert the serialized JSON always ends in `+00:00`/`Z`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from app.modules.ask.schemas import ConversationRead, ConversationTurnRead
from app.modules.assignments.schemas import (
    AssignmentRead,
    AssignmentSubmissionRead,
    RosterMember,
)
from app.modules.documents.models import DocumentStatus
from app.modules.documents.schemas import DocumentRead
from app.modules.flashcards.schemas import FlashcardRead
from app.modules.quiz.schemas import QuizRead
from app.modules.subjects.schemas import SubjectRead
from app.shared.datetime import UtcDatetime

# A value shaped exactly like one read back from the DB: tz-aware UTC written by
# `datetime.now(UTC)` but stripped to NAIVE by TIMESTAMP WITHOUT TIME ZONE.
NAIVE_UTC = datetime(2026, 7, 20, 13, 0, 0)


def _has_utc_marker(iso: str) -> bool:
    return iso.endswith("Z") or iso.endswith("+00:00")


class _Sample(BaseModel):
    when: UtcDatetime


def test_naive_datetime_serializes_with_utc_offset() -> None:
    dumped = json.loads(_Sample(when=NAIVE_UTC).model_dump_json())
    assert dumped["when"] == "2026-07-20T13:00:00+00:00"
    assert _has_utc_marker(dumped["when"])


def test_naive_datetime_without_annotation_has_no_marker() -> None:
    """Documents the bug the annotation fixes: a plain `datetime` field loses the zone."""

    class _Plain(BaseModel):
        when: datetime

    dumped = json.loads(_Plain(when=NAIVE_UTC).model_dump_json())
    assert not _has_utc_marker(dumped["when"])


def test_aware_datetime_keeps_offset() -> None:
    aware = datetime(2026, 7, 20, 13, 0, 0, tzinfo=UTC)
    dumped = json.loads(_Sample(when=aware).model_dump_json())
    assert _has_utc_marker(dumped["when"])


def test_quiz_read_created_at_is_utc() -> None:
    quiz = QuizRead(id=uuid.uuid4(), subject_id=uuid.uuid4(), title="Q", created_at=NAIVE_UTC)
    assert _has_utc_marker(json.loads(quiz.model_dump_json())["created_at"])


def test_subject_read_created_at_is_utc() -> None:
    subject = SubjectRead(id=uuid.uuid4(), name="S", org_id=None, created_at=NAIVE_UTC)
    assert _has_utc_marker(json.loads(subject.model_dump_json())["created_at"])


def test_document_read_created_at_is_utc() -> None:
    doc = DocumentRead(
        id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        filename="f.pdf",
        content_type="application/pdf",
        status=DocumentStatus.READY,
        summary=None,
        created_at=NAIVE_UTC,
    )
    assert _has_utc_marker(json.loads(doc.model_dump_json())["created_at"])


def test_conversation_read_created_at_is_utc() -> None:
    convo = ConversationRead(
        id=uuid.uuid4(), subject_id=uuid.uuid4(), title=None, created_at=NAIVE_UTC
    )
    assert _has_utc_marker(json.loads(convo.model_dump_json())["created_at"])


def test_conversation_turn_read_created_at_is_utc() -> None:
    turn = ConversationTurnRead(
        id=uuid.uuid4(), question="q", answer="a", sources=[], created_at=NAIVE_UTC
    )
    assert _has_utc_marker(json.loads(turn.model_dump_json())["created_at"])


def test_flashcard_read_all_datetimes_are_utc() -> None:
    card = FlashcardRead(
        id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        front="f",
        back="b",
        repetitions=0,
        ease_factor=2.5,
        interval_days=0,
        due_at=NAIVE_UTC,
        last_reviewed_at=NAIVE_UTC,
        created_at=NAIVE_UTC,
    )
    dumped = json.loads(card.model_dump_json())
    for field in ("due_at", "last_reviewed_at", "created_at"):
        assert _has_utc_marker(dumped[field]), field


def test_flashcard_read_optional_datetime_stays_null() -> None:
    card = FlashcardRead(
        id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        front="f",
        back="b",
        repetitions=0,
        ease_factor=2.5,
        interval_days=0,
        due_at=NAIVE_UTC,
        last_reviewed_at=None,
        created_at=NAIVE_UTC,
    )
    assert json.loads(card.model_dump_json())["last_reviewed_at"] is None


def test_assignment_read_datetimes_are_utc() -> None:
    assignment = AssignmentRead(
        id=uuid.uuid4(),
        org_id="org_1",
        owner_id="user_1",
        subject_id=uuid.uuid4(),
        quiz_id=None,
        title="A",
        description=None,
        due_at=NAIVE_UTC,
        created_at=NAIVE_UTC,
    )
    dumped = json.loads(assignment.model_dump_json())
    assert _has_utc_marker(dumped["due_at"])
    assert _has_utc_marker(dumped["created_at"])


def test_assignment_submission_and_roster_datetimes_are_utc() -> None:
    submission = AssignmentSubmissionRead(
        id=uuid.uuid4(),
        assignment_id=uuid.uuid4(),
        owner_id="user_1",
        completed_at=NAIVE_UTC,
        score=90,
        note=None,
    )
    assert _has_utc_marker(json.loads(submission.model_dump_json())["completed_at"])

    member = RosterMember(user_id="user_1", submitted=True, score=90, completed_at=NAIVE_UTC)
    assert _has_utc_marker(json.loads(member.model_dump_json())["completed_at"])


@pytest.mark.parametrize("value", [None])
def test_roster_member_optional_completed_at_stays_null(value: datetime | None) -> None:
    member = RosterMember(user_id="user_1", submitted=False, completed_at=value)
    assert json.loads(member.model_dump_json())["completed_at"] is None
