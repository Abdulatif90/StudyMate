"""Assignment roster-diff endpoint tests — Phase 5 (who hasn't submitted).

The roster endpoint (`GET /assignments/{id}/roster`) is the first backend path that calls
Clerk's Backend API. These tests MOCK that client (`clerk_api.list_organization_member_ids`)
— never hitting real Clerk, same offline discipline as the rest of the suite — and prove:
the teacher gate (404 cross-org, 403 plain member) runs BEFORE any Clerk call, the diff is
wired correctly, and a MISSING Clerk key surfaces as a clean 503 (not a 500 leak).

Same isolated-SQLite + dependency-override pattern as `test_assignments.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core import clerk_api
from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app

TEACHER = "user_teacher_O"
STUDENT = "user_student_O"
STUDENT2 = "user_student2_O"
OTHER_ORG_TEACHER = "user_teacher_O2"

ORG_O = "org_O"
ORG_O2 = "org_O2"
_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


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


def _mock_members(monkeypatch, member_ids: list[str]) -> None:
    """Replace the Clerk client so no real network call is made."""
    monkeypatch.setattr(clerk_api, "list_organization_member_ids", lambda org_id: list(member_ids))


def _make_assignment() -> str:
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = client.post("/subjects", json={"name": "Shared Biology"})
    assert subject.status_code == 201, subject.text
    created = client.post(
        "/assignments", json={"title": "Read ch.1", "subject_id": subject.json()["id"]}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _submit_as(assignment_id: str, user_id: str, score: int | None = None) -> None:
    _act_as(user_id, ORG_O, _ROLE_MEMBER)
    payload = {"score": score} if score is not None else {}
    response = client.post(f"/assignments/{assignment_id}/submit", json=payload)
    assert response.status_code == 201, response.text


def test_teacher_gets_roster_diff(monkeypatch):
    assignment_id = _make_assignment()
    _submit_as(assignment_id, STUDENT, score=88)
    # Org has three members; only STUDENT submitted.
    _mock_members(monkeypatch, [TEACHER, STUDENT, STUDENT2])

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.get(f"/assignments/{assignment_id}/roster")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["assignment_id"] == assignment_id
    assert body["total_members"] == 3
    assert body["submitted_count"] == 1
    assert body["not_submitted_count"] == 2
    assert [m["user_id"] for m in body["submitted"]] == [STUDENT]
    assert body["submitted"][0]["score"] == 88
    assert {m["user_id"] for m in body["not_submitted"]} == {TEACHER, STUDENT2}
    assert all(m["submitted"] is False for m in body["not_submitted"])


def test_roster_all_members_still_owe_when_none_submitted(monkeypatch):
    assignment_id = _make_assignment()
    _mock_members(monkeypatch, [TEACHER, STUDENT, STUDENT2])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    body = client.get(f"/assignments/{assignment_id}/roster").json()
    assert body["submitted_count"] == 0
    assert body["not_submitted_count"] == 3


def test_plain_member_forbidden_before_any_clerk_call(monkeypatch):
    assignment_id = _make_assignment()

    # If the gate leaked past the role check, this would raise instead of 403.
    def _boom(org_id):
        raise AssertionError("Clerk must not be called for a non-teacher")

    monkeypatch.setattr(clerk_api, "list_organization_member_ids", _boom)
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.get(f"/assignments/{assignment_id}/roster").status_code == 403


def test_cross_org_teacher_404_before_any_clerk_call(monkeypatch):
    assignment_id = _make_assignment()

    def _boom(org_id):
        raise AssertionError("Clerk must not be called for a cross-org caller")

    monkeypatch.setattr(clerk_api, "list_organization_member_ids", _boom)
    _act_as(OTHER_ORG_TEACHER, ORG_O2, _ROLE_ADMIN)
    assert client.get(f"/assignments/{assignment_id}/roster").status_code == 404


def test_missing_clerk_key_returns_503_not_500(monkeypatch):
    # Simulate an unconfigured server: the Clerk client raises ClerkConfigError exactly as
    # it does when CLERK_SECRET_KEY is unset (see test_clerk_api for the real gating). The
    # router MUST translate that to a clean 503, never a 500 leak. Mocked so the test is
    # deterministic and offline regardless of whatever is in the ambient .env.
    assignment_id = _make_assignment()

    def _unconfigured(org_id):
        raise clerk_api.ClerkConfigError("CLERK_SECRET_KEY is not set.")

    monkeypatch.setattr(clerk_api, "list_organization_member_ids", _unconfigured)
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.get(f"/assignments/{assignment_id}/roster")
    assert response.status_code == 503, response.text
    assert "Clerk" in response.json()["detail"]


def test_upstream_clerk_failure_returns_502(monkeypatch):
    assignment_id = _make_assignment()

    def _fail(org_id):
        raise clerk_api.ClerkAPIError("boom")

    monkeypatch.setattr(clerk_api, "list_organization_member_ids", _fail)
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    assert client.get(f"/assignments/{assignment_id}/roster").status_code == 502


def test_roster_surfaces_ex_member_submitter(monkeypatch):
    # STUDENT2 submitted then left the org (not in the member list) — still surfaced.
    assignment_id = _make_assignment()
    _submit_as(assignment_id, STUDENT, score=70)
    _submit_as(assignment_id, STUDENT2, score=55)
    _mock_members(monkeypatch, [TEACHER, STUDENT])

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    body = client.get(f"/assignments/{assignment_id}/roster").json()
    submitted_ids = {m["user_id"] for m in body["submitted"]}
    assert submitted_ids == {STUDENT, STUDENT2}
    assert body["total_members"] == 2  # ex-member NOT counted in current membership
    assert body["submitted_count"] == 2
    assert [m["user_id"] for m in body["not_submitted"]] == [TEACHER]
