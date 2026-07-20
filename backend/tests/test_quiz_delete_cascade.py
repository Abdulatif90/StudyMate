"""Regression tests for the production 500 where deleting a quiz — or a subject
containing one — that is referenced by an `assignment` or by `quiz_attempts` violated a
foreign key (`assignments_quiz_id_fkey` / `quiz_attempts_quiz_id_fkey`, and the subject's
own `assignments_subject_id_fkey`).

`delete_quiz` used to delete only the quiz + its questions, leaving assignment / attempt
rows that still pointed at the quiz; flushing the quiz DELETE then blew up on the FK. The
subject-delete cascade runs through `delete_quiz`, so the whole subject delete 500'd too.

**Foreign keys are turned ON for this module's SQLite engine** (`PRAGMA foreign_keys=ON`
via a connect listener) — SQLite ignores FKs by default, so without this the orphaned
rows would linger silently and never reproduce the Postgres `IntegrityError` these tests
exist to lock down. With FKs on, the pre-fix code raises on the quiz/subject DELETE; the
post-fix code deletes the referencing rows first and succeeds.

Same offline, isolated-SQLite pattern as `test_quiz_attempts.py`: per-test dependency
overrides for `get_session`/`get_current_user_id`/`get_org_context`, identity switched via
`_act_as`, all rows seeded directly (no network).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.assignments.models import Assignment, AssignmentSubmission
from app.modules.quiz.models import Quiz, QuizAttempt, QuizQuestion
from app.modules.subjects.models import Subject

TEACHER = "user_teacher_O"
STUDENT = "user_student_O"

ORG_O = "org_O"
_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@event.listens_for(_engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    """SQLite enforces foreign keys only when asked, per connection. Turn them on so this
    module actually reproduces the Postgres FK violation instead of silently orphaning
    rows."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _get_test_session():
    with Session(_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _isolated_db():
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user_id, None)
    app.dependency_overrides.pop(get_org_context, None)
    SQLModel.metadata.drop_all(_engine)


client = TestClient(app)


def _act_as(user_id: str, org_id: str | None, org_role: str | None) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_org_context] = lambda: OrgContext(org_id=org_id, org_role=org_role)


def _create_org_subject(name: str = "Shared Biology") -> str:
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["org_id"] == ORG_O
    return body["id"]


def _seed_quiz_with_question(owner_id: str, subject_id: str) -> str:
    with Session(_engine) as session:
        quiz = Quiz(subject_id=uuid.UUID(subject_id), owner_id=owner_id, title="Q")
        session.add(quiz)
        session.commit()
        session.refresh(quiz)
        session.add(
            QuizQuestion(
                quiz_id=quiz.id,
                owner_id=owner_id,
                question="Q0",
                options=["A", "B"],
                correct_index=0,
                order=0,
            )
        )
        session.commit()
        return str(quiz.id)


def _seed_assignment(org_id: str, owner_id: str, subject_id: str, quiz_id: str | None) -> str:
    with Session(_engine) as session:
        assignment = Assignment(
            org_id=org_id,
            owner_id=owner_id,
            subject_id=uuid.UUID(subject_id),
            quiz_id=uuid.UUID(quiz_id) if quiz_id else None,
            title="Do it",
        )
        session.add(assignment)
        session.commit()
        session.refresh(assignment)
        return str(assignment.id)


def _seed_submission(assignment_id: str, owner_id: str) -> None:
    with Session(_engine) as session:
        session.add(AssignmentSubmission(assignment_id=uuid.UUID(assignment_id), owner_id=owner_id))
        session.commit()


def _seed_attempt(quiz_id: str, subject_id: str, owner_id: str) -> None:
    with Session(_engine) as session:
        session.add(
            QuizAttempt(
                quiz_id=uuid.UUID(quiz_id),
                subject_id=uuid.UUID(subject_id),
                owner_id=owner_id,
                correct=1,
                total=1,
            )
        )
        session.commit()


def _counts() -> dict[str, int]:
    with Session(_engine) as session:
        return {
            "subjects": len(list(session.exec(select(Subject)))),
            "quizzes": len(list(session.exec(select(Quiz)))),
            "questions": len(list(session.exec(select(QuizQuestion)))),
            "attempts": len(list(session.exec(select(QuizAttempt)))),
            "assignments": len(list(session.exec(select(Assignment)))),
            "submissions": len(list(session.exec(select(AssignmentSubmission)))),
        }


# ---------------------------------------------------------------------------
# Deleting a quiz referenced by an assignment + attempts.
# ---------------------------------------------------------------------------


def test_delete_quiz_with_assignment_and_attempts_succeeds():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz_with_question(TEACHER, subject_id)
    assignment_id = _seed_assignment(ORG_O, TEACHER, subject_id, quiz_id)
    _seed_submission(assignment_id, STUDENT)
    _seed_attempt(quiz_id, subject_id, STUDENT)

    # Pre-fix this DELETE 500'd on assignments_quiz_id_fkey / quiz_attempts_quiz_id_fkey.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.delete(f"/subjects/{subject_id}/quizzes/{quiz_id}")
    assert response.status_code == 204, response.text

    counts = _counts()
    # Quiz + its questions gone, and every referencing row (assignment, its submission,
    # the attempt) gone too — the subject itself untouched.
    assert counts["quizzes"] == 0
    assert counts["questions"] == 0
    assert counts["attempts"] == 0
    assert counts["assignments"] == 0
    assert counts["submissions"] == 0
    assert counts["subjects"] == 1


# ---------------------------------------------------------------------------
# Deleting a SUBJECT that contains such a quiz — the cascade path that 500'd in prod.
# ---------------------------------------------------------------------------


def test_delete_subject_with_referenced_quiz_and_bare_assignment_succeeds():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz_with_question(TEACHER, subject_id)
    # A quiz-linked assignment (with a submission) + an attempt on the quiz...
    linked_assignment = _seed_assignment(ORG_O, TEACHER, subject_id, quiz_id)
    _seed_submission(linked_assignment, STUDENT)
    _seed_attempt(quiz_id, subject_id, STUDENT)
    # ...PLUS a bare assignment over the subject with NO quiz link, which references the
    # subject directly via assignments.subject_id (the second dangling FK the subject
    # cascade must clean).
    bare_assignment = _seed_assignment(ORG_O, TEACHER, subject_id, None)
    _seed_submission(bare_assignment, STUDENT)

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.delete(f"/subjects/{subject_id}")
    assert response.status_code == 204, response.text

    # The whole subject and everything under it is gone — no FK violation anywhere.
    assert _counts() == {
        "subjects": 0,
        "quizzes": 0,
        "questions": 0,
        "attempts": 0,
        "assignments": 0,
        "submissions": 0,
    }
