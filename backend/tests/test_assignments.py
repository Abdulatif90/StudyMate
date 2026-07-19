"""Assignment foundation tests — Phase 5 increment 3a (teacher assigns to org).

Security-critical shape: an assignment is broadcast to the creator's active org and must
be visible to *every* member of that org — but NEVER leak across org boundaries, and a
caller with no active org must see nothing. These tests prove both the happy paths and
the isolation guarantees.

Same offline, isolated-SQLite pattern as `test_org_quizzes.py`: `app.dependency_overrides`
swaps `get_session`, `get_current_user_id`, and `get_org_context` per test; identity is
switched mid-test via `_act_as`. No network — subjects/quizzes are created via the real
routes (subject creation) or seeded directly (quiz rows).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.assignments.models import Assignment, AssignmentSubmission
from app.modules.quiz.models import Quiz

# --- Identities -------------------------------------------------------------
# Org O: a teacher (admin) who owns the shared subject + creates assignments, a second
# teacher, and a plain student member. Org O2: a separate org whose members must never
# see O's assignments.
TEACHER = "user_teacher_O"
TEACHER2 = "user_teacher2_O"
STUDENT = "user_student_O"
OTHER_ORG_TEACHER = "user_teacher_O2"
OTHER_ORG_STUDENT = "user_student_O2"
LONER = "user_no_org"  # signed in, no active organization

ORG_O = "org_O"
ORG_O2 = "org_O2"

_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)

_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _get_test_session():
    with Session(_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _isolated_db():
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)  # default identity; tests switch via _act_as
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
    """Teacher of org O creates a subject → published to the org (org_id set)."""
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["org_id"] == ORG_O
    return body["id"]


def _create_private_subject(owner: str = STUDENT) -> str:
    """A member (no teacher role) creates a subject → PRIVATE (org_id None)."""
    _act_as(owner, ORG_O, _ROLE_MEMBER)
    response = client.post("/subjects", json={"name": "Private notes"})
    assert response.status_code == 201, response.text
    assert response.json()["org_id"] is None
    return response.json()["id"]


def _seed_quiz(owner_id: str, subject_id: str) -> str:
    """Insert a quiz row directly (no generation network call)."""
    with Session(_engine) as session:
        quiz = Quiz(subject_id=uuid.UUID(subject_id), owner_id=owner_id, title="Q")
        session.add(quiz)
        session.commit()
        session.refresh(quiz)
        return str(quiz.id)


def _create_assignment(subject_id: str, **extra) -> tuple[int, dict]:
    payload = {"title": "Read chapter 1", "subject_id": subject_id, **extra}
    response = client.post("/assignments", json=payload)
    return response.status_code, response.json() if response.content else {}


# ---------------------------------------------------------------------------
# Create — teacher only, over a writable org subject.
# ---------------------------------------------------------------------------


def test_teacher_creates_assignment_over_org_subject():
    subject_id = _create_org_subject()
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, body = _create_assignment(subject_id, description="Due soon")

    assert status_code == 201, body
    assert body["org_id"] == ORG_O
    assert body["owner_id"] == TEACHER
    assert body["subject_id"] == subject_id
    assert body["quiz_id"] is None
    assert body["description"] == "Due soon"


def test_student_member_cannot_create_assignment():
    # require_teacher → 403 for a plain member, before any service logic runs.
    subject_id = _create_org_subject()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    status_code, _ = _create_assignment(subject_id)
    assert status_code == 403


def test_loner_with_no_active_org_cannot_create_assignment():
    subject_id = _create_org_subject()
    _act_as(LONER, None, None)
    status_code, _ = _create_assignment(subject_id)
    assert status_code == 403


def test_teacher_cannot_assign_over_private_subject():
    # A private subject the teacher can't even read → require_writable_subject 404s.
    private_id = _create_private_subject(owner=STUDENT)
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, _ = _create_assignment(private_id)
    assert status_code == 404


def test_teacher_cannot_assign_over_other_orgs_subject():
    # Subject owned by ORG_O; a teacher of ORG_O2 can't read it → 404.
    subject_id = _create_org_subject()
    _act_as(OTHER_ORG_TEACHER, ORG_O2, _ROLE_ADMIN)
    status_code, _ = _create_assignment(subject_id)
    assert status_code == 404


# ---------------------------------------------------------------------------
# Optional quiz link validation.
# ---------------------------------------------------------------------------


def test_assignment_with_valid_quiz_link():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id)
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, body = _create_assignment(subject_id, quiz_id=quiz_id)
    assert status_code == 201, body
    assert body["quiz_id"] == quiz_id


def test_assignment_quiz_link_rejected_when_other_subject():
    subject_id = _create_org_subject()
    other_subject_id = _create_org_subject("Shared Chemistry")
    quiz_id = _seed_quiz(TEACHER, other_subject_id)  # quiz over a DIFFERENT subject
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, _ = _create_assignment(subject_id, quiz_id=quiz_id)
    assert status_code == 400


def test_assignment_quiz_link_rejected_when_not_teachers_quiz():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(STUDENT, subject_id)  # student's own quiz, not the teacher's
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, _ = _create_assignment(subject_id, quiz_id=quiz_id)
    assert status_code == 400


def test_assignment_quiz_link_rejected_when_nonexistent():
    subject_id = _create_org_subject()
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, _ = _create_assignment(subject_id, quiz_id=_MISSING_ID)
    assert status_code == 400


# ---------------------------------------------------------------------------
# List / get — org-scoped broadcast, no cross-org leak.
# ---------------------------------------------------------------------------


def _make_one_assignment() -> str:
    subject_id = _create_org_subject()
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    status_code, body = _create_assignment(subject_id)
    assert status_code == 201, body
    return body["id"]


def test_member_of_same_org_sees_assignment():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    listed = client.get("/assignments")
    assert listed.status_code == 200
    assert assignment_id in {a["id"] for a in listed.json()}
    got = client.get(f"/assignments/{assignment_id}")
    assert got.status_code == 200
    assert got.json()["id"] == assignment_id


def test_member_of_different_org_sees_empty_list_and_404():
    assignment_id = _make_one_assignment()
    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.get("/assignments").json() == []
    assert client.get(f"/assignments/{assignment_id}").status_code == 404


def test_loner_with_no_active_org_sees_empty_list_and_404():
    assignment_id = _make_one_assignment()
    _act_as(LONER, None, None)
    assert client.get("/assignments").json() == []
    assert client.get(f"/assignments/{assignment_id}").status_code == 404


def test_list_is_ordered_newest_first():
    subject_id = _create_org_subject()
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    ids = [_create_assignment(subject_id, title=f"A{i}")[1]["id"] for i in range(3)]
    listed = [a["id"] for a in client.get("/assignments").json()]
    # Every created assignment appears; the set is exactly the org's, no extras.
    assert set(listed) == set(ids)


# ---------------------------------------------------------------------------
# Delete — creator or any teacher of the org; forbidden for a plain member.
# ---------------------------------------------------------------------------


def test_creator_can_delete_own_assignment():
    assignment_id = _make_one_assignment()
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    assert client.delete(f"/assignments/{assignment_id}").status_code == 204
    with Session(_engine) as session:
        assert session.get(Assignment, uuid.UUID(assignment_id)) is None


def test_another_teacher_of_same_org_can_delete():
    assignment_id = _make_one_assignment()
    _act_as(TEACHER2, ORG_O, _ROLE_ADMIN)  # not the creator, but a teacher of the org
    assert client.delete(f"/assignments/{assignment_id}").status_code == 204


def test_plain_member_cannot_delete_assignment():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.delete(f"/assignments/{assignment_id}").status_code == 403
    with Session(_engine) as session:
        assert session.get(Assignment, uuid.UUID(assignment_id)) is not None  # still there


def test_teacher_of_different_org_gets_404_on_delete():
    # 404 hides existence — a wrong-org caller must not learn the assignment exists.
    assignment_id = _make_one_assignment()
    _act_as(OTHER_ORG_TEACHER, ORG_O2, _ROLE_ADMIN)
    assert client.delete(f"/assignments/{assignment_id}").status_code == 404
    with Session(_engine) as session:
        assert session.get(Assignment, uuid.UUID(assignment_id)) is not None  # still there


# ---------------------------------------------------------------------------
# Submission — a student marks complete (owner-scoped, org-gated, idempotent).
# ---------------------------------------------------------------------------


def test_student_submits_creating_one_owned_row():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = client.post(f"/assignments/{assignment_id}/submit", json={"score": 90})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assignment_id"] == assignment_id
    assert body["owner_id"] == STUDENT
    assert body["score"] == 90
    with Session(_engine) as session:
        rows = list(session.exec(select(AssignmentSubmission)))
        assert len(rows) == 1
        assert rows[0].owner_id == STUDENT
        assert rows[0].assignment_id == uuid.UUID(assignment_id)


def test_resubmit_is_idempotent_updates_same_row():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    first = client.post(f"/assignments/{assignment_id}/submit", json={"score": 50})
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post(
        f"/assignments/{assignment_id}/submit", json={"score": 88, "note": "redid it"}
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first_id  # same row, not a duplicate
    assert second.json()["score"] == 88
    assert second.json()["note"] == "redid it"
    with Session(_engine) as session:
        rows = list(session.exec(select(AssignmentSubmission)))
        assert len(rows) == 1  # unique (assignment, owner) held — no second row


def test_two_students_each_get_their_own_submission():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.post(f"/assignments/{assignment_id}/submit", json={}).status_code == 201
    _act_as(TEACHER2, ORG_O, _ROLE_ADMIN)  # a second acting user in the org
    assert client.post(f"/assignments/{assignment_id}/submit", json={}).status_code == 201
    with Session(_engine) as session:
        rows = list(session.exec(select(AssignmentSubmission)))
        assert {r.owner_id for r in rows} == {STUDENT, TEACHER2}


def test_student_of_different_org_cannot_submit():
    assignment_id = _make_one_assignment()
    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.post(f"/assignments/{assignment_id}/submit", json={}).status_code == 404
    with Session(_engine) as session:
        assert list(session.exec(select(AssignmentSubmission))) == []  # nothing written


def test_loner_with_no_active_org_cannot_submit():
    assignment_id = _make_one_assignment()
    _act_as(LONER, None, None)
    assert client.post(f"/assignments/{assignment_id}/submit", json={}).status_code == 404


def test_submit_score_out_of_range_rejected():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = client.post(f"/assignments/{assignment_id}/submit", json={"score": 101})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Teacher view — lists every student's submission; teacher/admin only; org-gated.
# ---------------------------------------------------------------------------


def _seed_two_submissions(assignment_id: str) -> None:
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    r1 = client.post(f"/assignments/{assignment_id}/submit", json={"score": 70})
    assert r1.status_code == 201
    _act_as(TEACHER2, ORG_O, _ROLE_ADMIN)
    r2 = client.post(f"/assignments/{assignment_id}/submit", json={})
    assert r2.status_code == 201


def test_teacher_views_all_submissions():
    assignment_id = _make_one_assignment()
    _seed_two_submissions(assignment_id)
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.get(f"/assignments/{assignment_id}/submissions")
    assert response.status_code == 200, response.text
    owners = {s["owner_id"] for s in response.json()}
    assert owners == {STUDENT, TEACHER2}


def test_plain_member_cannot_view_submissions():
    assignment_id = _make_one_assignment()
    _seed_two_submissions(assignment_id)
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.get(f"/assignments/{assignment_id}/submissions").status_code == 403


def test_teacher_of_different_org_gets_404_on_submissions():
    # 404 hides existence — the wrong-org teacher must not learn the assignment exists.
    assignment_id = _make_one_assignment()
    _seed_two_submissions(assignment_id)
    _act_as(OTHER_ORG_TEACHER, ORG_O2, _ROLE_ADMIN)
    assert client.get(f"/assignments/{assignment_id}/submissions").status_code == 404


# ---------------------------------------------------------------------------
# my-submission — owner-scoped; never another student's.
# ---------------------------------------------------------------------------


def test_my_submission_returns_own_only():
    assignment_id = _make_one_assignment()
    _seed_two_submissions(assignment_id)
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = client.get(f"/assignments/{assignment_id}/my-submission")
    assert response.status_code == 200, response.text
    assert response.json()["owner_id"] == STUDENT  # own row, never TEACHER2's


def test_my_submission_404_when_none():
    assignment_id = _make_one_assignment()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)  # hasn't submitted
    assert client.get(f"/assignments/{assignment_id}/my-submission").status_code == 404


def test_my_submission_404_for_other_org():
    assignment_id = _make_one_assignment()
    _seed_two_submissions(assignment_id)
    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    # Can't even probe an assignment outside their org.
    assert client.get(f"/assignments/{assignment_id}/my-submission").status_code == 404


# ---------------------------------------------------------------------------
# Delete cascade — an assignment's submissions go with it (no FK violation).
# ---------------------------------------------------------------------------


def test_delete_assignment_cascades_submissions():
    assignment_id = _make_one_assignment()
    _seed_two_submissions(assignment_id)
    with Session(_engine) as session:
        assert len(list(session.exec(select(AssignmentSubmission)))) == 2

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    assert client.delete(f"/assignments/{assignment_id}").status_code == 204  # no FK 500

    with Session(_engine) as session:
        assert session.get(Assignment, uuid.UUID(assignment_id)) is None
        assert list(session.exec(select(AssignmentSubmission))) == []  # cascaded away
