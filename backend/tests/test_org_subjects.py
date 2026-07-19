"""Cross-tenant isolation tests for org-owned (read-shared) subjects — Phase 5
increment 2. THE highest-risk area in the codebase: a bug here leaks one org's (or one
user's) private study material to another, so isolation is tested exhaustively.

Same offline, isolated-SQLite pattern as the rest of the suite: `app.dependency_overrides`
swaps `get_session`, `get_current_user_id`, and `get_org_context` per test. Identity
(who am I + which org is active) is switched mid-test via `_act_as`, mirroring how
test_subjects.py already reassigns `get_current_user_id` inline.

R2 + Inngest + Claude are stubbed so nothing hits the network; document chunks (for the
Ask/RAG path) are inserted directly with a dummy embedding — on SQLite `search_chunks`
returns filtered-but-unranked chunks (no Cohere), which is exactly enough to prove the
access scoping (the real ranking is covered by the live tests in test_search/test_ask).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core import r2_client
from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.ask import service as ask_service
from app.modules.documents import service as documents_service
from app.modules.documents.embedding import EMBEDDING_DIM
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.subjects.models import Subject

# --- Identities -------------------------------------------------------------
# Org O: a teacher (admin) who owns its shared content, plus a plain student member.
# Org O2: a separate org whose student must never see O's content.
TEACHER = "user_teacher_O"
STUDENT = "user_student_O"
OTHER_ORG_STUDENT = "user_student_O2"
LONER = "user_no_org"  # signed in, no active organization

ORG_O = "org_O"
ORG_O2 = "org_O2"

_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"
# CONFIRMED AT RUNTIME (via `GET /org`) that Clerk can also emit the role claim as
# this bare, unprefixed slug rather than `org:admin` — this was the exact shape
# that broke teacher detection (see docs/DECISIONS.md ADR #9), so it gets its own
# coverage below alongside the prefixed-form cases.
_ROLE_ADMIN_BARE = "admin"

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
    # Default identity: the teacher of org O with an active-org context. Individual
    # tests switch identity via `_act_as`.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user_id, None)
    app.dependency_overrides.pop(get_org_context, None)
    SQLModel.metadata.drop_all(_engine)


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    """R2 in-memory + Inngest enqueue no-op — so the upload write path runs without any
    network. Document processing (Cohere embed) is never triggered here; chunks are
    inserted directly where the Ask path needs them."""
    store: dict[str, bytes] = {}

    def _put(key, data, content_type):
        store[key] = data

    monkeypatch.setattr(r2_client, "put_object", _put)
    monkeypatch.setattr(r2_client, "get_object", lambda key: store[key])
    monkeypatch.setattr(r2_client, "delete_object", lambda key: store.pop(key, None))
    monkeypatch.setattr(documents_service, "enqueue_document_processing", lambda document: None)


client = TestClient(app)


def _act_as(user_id: str, org_id: str | None, org_role: str | None) -> None:
    """Switch the authenticated caller AND their active-org context for subsequent
    requests — the whole point of these tests is that access changes with identity."""
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_org_context] = lambda: OrgContext(org_id=org_id, org_role=org_role)


def _create_subject(name: str) -> dict:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _seed_document_with_chunk(subject_id: str, owner_id: str, *, text: str) -> uuid.UUID:
    """Insert a ready Document + one embedded chunk directly (no upload pipeline) so the
    Ask/RAG read path has retrievable material owned by `owner_id`."""
    with Session(_engine) as session:
        document = Document(
            subject_id=uuid.UUID(subject_id),
            owner_id=owner_id,
            filename="material.txt",
            content_type="text/plain",
            status=DocumentStatus.READY,
            r2_object_key=f"{owner_id}/{subject_id}/material.txt",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        session.add(
            DocumentChunk(
                document_id=document.id,
                subject_id=uuid.UUID(subject_id),
                owner_id=owner_id,
                chunk_index=0,
                text=text,
                embedding=[0.1] * EMBEDDING_DIM,
            )
        )
        session.commit()
        return document.id


# ---------------------------------------------------------------------------
# Baseline: private subjects are unchanged.
# ---------------------------------------------------------------------------


def test_member_without_teacher_role_creates_private_subject():
    # A plain member (student) of org O must NOT be able to publish to the whole org.
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    created = _create_subject("Student's own notes")
    assert created["org_id"] is None  # private, despite an active org

    # ...and it's invisible to another member of the same org.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    ids = [s["id"] for s in client.get("/subjects").json()]
    assert created["id"] not in ids


def test_loner_with_no_active_org_creates_private_subject():
    _act_as(LONER, None, None)
    created = _create_subject("Personal")
    assert created["org_id"] is None
    assert client.get(f"/subjects/{created['id']}").status_code == 200


# ---------------------------------------------------------------------------
# Teacher creates an org subject; members of the SAME org can read it + Ask.
# ---------------------------------------------------------------------------


def test_teacher_creates_org_subject_and_member_can_read_it_and_its_documents():
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("Shared Biology")
    assert subject["org_id"] == ORG_O  # published to the org
    _seed_document_with_chunk(subject["id"], TEACHER, text="Mitochondria are the powerhouse.")

    # The student member of O reads the subject...
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    got = client.get(f"/subjects/{subject['id']}")
    assert got.status_code == 200
    assert got.json()["org_id"] == ORG_O

    # ...and its (teacher-owned) documents, via the subject-scoped read path.
    docs = client.get(f"/subjects/{subject['id']}/documents")
    assert docs.status_code == 200
    assert [d["filename"] for d in docs.json()] == ["material.txt"]

    # ...and it appears in their subject listing (own + active org's).
    assert subject["id"] in [s["id"] for s in client.get("/subjects").json()]


def test_teacher_with_bare_admin_role_can_create_and_write_org_subject():
    # The exact runtime bug: a real Clerk session emitted `org_role: "admin"` (bare,
    # no `org:` prefix), which `is_teacher_role` used to reject outright, silently
    # demoting an actual org admin to "student" and blocking org content writes.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN_BARE)
    subject = _create_subject("Shared Physics (bare role)")
    assert subject["org_id"] == ORG_O  # published to the org, not private

    assert _upload(subject["id"]).status_code == 201
    assert client.delete(f"/subjects/{subject['id']}").status_code == 204


def test_member_can_ask_over_an_org_subject(monkeypatch):
    monkeypatch.setattr(
        ask_service, "ask_claude", lambda question, chunks, prior_turns: "Grounded answer."
    )
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("Shared Chem")
    _seed_document_with_chunk(subject["id"], TEACHER, text="Water is H2O.")

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = client.post(f"/subjects/{subject['id']}/ask", json={"question": "What is water?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Grounded answer."
    # Retrieval actually reached the teacher-owned chunk (not owner-filtered away).
    assert [s["text"] for s in body["sources"]] == ["Water is H2O."]

    # The conversation created belongs to the STUDENT, not the teacher/owner.
    conv_id = body["conversation_id"]
    with Session(_engine) as session:
        assert ask_service.get_conversation(session, STUDENT, uuid.UUID(conv_id)) is not None
        assert ask_service.get_conversation(session, TEACHER, uuid.UUID(conv_id)) is None


# ---------------------------------------------------------------------------
# Cross-org isolation: a member of a DIFFERENT org sees nothing of O's.
# ---------------------------------------------------------------------------


def test_different_org_member_cannot_see_or_read_or_ask_over_org_subject(monkeypatch):
    monkeypatch.setattr(
        ask_service, "ask_claude", lambda question, chunks, prior_turns: "should never run"
    )
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("O's Private-to-O2 Material")
    _seed_document_with_chunk(subject["id"], TEACHER, text="Secret to org O only.")

    # A student whose ACTIVE org is O2 — never O.
    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.get(f"/subjects/{subject['id']}").status_code == 404
    assert client.get(f"/subjects/{subject['id']}/documents").status_code == 404
    ask = client.post(f"/subjects/{subject['id']}/ask", json={"question": "Tell me the secret"})
    assert ask.status_code == 404
    # Not in their listing either.
    assert subject["id"] not in [s["id"] for s in client.get("/subjects").json()]


def test_no_active_org_user_cannot_see_or_read_org_subject():
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("Org-only material")

    _act_as(LONER, None, None)
    assert client.get(f"/subjects/{subject['id']}").status_code == 404
    assert client.get(f"/subjects/{subject['id']}/documents").status_code == 404
    assert subject["id"] not in [s["id"] for s in client.get("/subjects").json()]


# ---------------------------------------------------------------------------
# Write denial: a plain member can read but never modify an org subject.
# ---------------------------------------------------------------------------


def _upload(subject_id: str):
    return client.post(
        f"/subjects/{subject_id}/documents",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )


def test_student_member_cannot_upload_to_or_delete_org_subject():
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("Shared, teacher-writable only")
    document_id = _seed_document_with_chunk(subject["id"], TEACHER, text="x")

    # Student member of O can READ but gets 403 on writes (they know it exists — honest).
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.get(f"/subjects/{subject['id']}").status_code == 200
    assert _upload(subject["id"]).status_code == 403
    assert client.delete(f"/subjects/{subject['id']}/documents/{document_id}").status_code == 403
    assert client.delete(f"/subjects/{subject['id']}").status_code == 403

    # The teacher/owner can.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    assert _upload(subject["id"]).status_code == 201
    assert client.delete(f"/subjects/{subject['id']}").status_code == 204


def test_different_org_member_gets_404_not_403_on_write():
    # A caller who can't even READ the subject must not learn it exists via a 403 —
    # writes deny with 404, same as reads.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("O material")

    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert _upload(subject["id"]).status_code == 404
    assert client.delete(f"/subjects/{subject['id']}").status_code == 404


# ---------------------------------------------------------------------------
# The owner's OTHER private subject never leaks to org members.
# ---------------------------------------------------------------------------


def test_owners_other_private_subject_is_never_exposed_to_org_members():
    # The teacher has BOTH an org subject and a separate private one. Toggling active
    # org must not turn the private one into shared content.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    org_subject = _create_subject("Shared")
    # Create a private subject directly with org_id=None owned by the teacher (a teacher
    # can only create org subjects through the API while an org is active, so seed this
    # one directly to represent their personal, non-org material).
    with Session(_engine) as session:
        private = Subject(owner_id=TEACHER, name="Teacher's private", org_id=None)
        session.add(private)
        session.commit()
        session.refresh(private)
        private_id = str(private.id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    listing_ids = [s["id"] for s in client.get("/subjects").json()]
    assert org_subject["id"] in listing_ids  # shared one is visible
    assert private_id not in listing_ids  # private one is NOT
    assert client.get(f"/subjects/{private_id}").status_code == 404
    assert client.get(f"/subjects/{private_id}/documents").status_code == 404


def test_teacher_of_a_different_org_cannot_write_to_this_orgs_subject():
    # Being a teacher is not enough — you must be a teacher of THAT org. A teacher whose
    # active org is O2 can't even read O's subject, so it's a 404.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    subject = _create_subject("O only")

    _act_as("teacher_of_O2", ORG_O2, _ROLE_ADMIN)
    assert client.get(f"/subjects/{subject['id']}").status_code == 404
    assert _upload(subject["id"]).status_code == 404


# ---------------------------------------------------------------------------
# GET /org — the Step 0 verification endpoint (org claims reaching the backend).
# ---------------------------------------------------------------------------


def test_org_endpoint_reports_active_org_context():
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    body = client.get("/org").json()
    assert body == {
        "user_id": TEACHER,
        "org_id": ORG_O,
        "org_role": _ROLE_ADMIN,
        "capability": "teacher",
    }


def test_org_endpoint_reports_no_org_for_personal_workspace():
    _act_as(LONER, None, None)
    body = client.get("/org").json()
    assert body == {
        "user_id": LONER,
        "org_id": None,
        "org_role": None,
        "capability": "student",
    }


# ---------------------------------------------------------------------------
# Pure authorization predicates (no DB / no I/O) — the single source of truth every
# read/write path routes through, so it's exhaustively covered in isolation.
# ---------------------------------------------------------------------------


def _subject(owner_id: str, org_id: str | None) -> Subject:
    return Subject(owner_id=owner_id, org_id=org_id, name="s")


def test_can_read_subject_owner_always_can():
    from app.modules.subjects.service import can_read_subject

    # Owner reads their private subject regardless of active org.
    assert can_read_subject(_subject("u1", None), "u1", None) is True
    assert can_read_subject(_subject("u1", None), "u1", ORG_O) is True
    # Owner reads their own org subject too.
    assert can_read_subject(_subject("u1", ORG_O), "u1", ORG_O) is True


def test_can_read_subject_org_member_can_only_when_active_org_matches():
    from app.modules.subjects.service import can_read_subject

    org_subject = _subject("teacher", ORG_O)
    assert can_read_subject(org_subject, "member", ORG_O) is True  # same active org
    assert can_read_subject(org_subject, "member", ORG_O2) is False  # different org
    assert can_read_subject(org_subject, "member", None) is False  # no active org


def test_can_read_subject_private_never_leaks_to_non_owner():
    from app.modules.subjects.service import can_read_subject

    private = _subject("owner", None)
    assert can_read_subject(private, "someone_else", None) is False
    assert can_read_subject(private, "someone_else", ORG_O) is False
    # The load-bearing None==None guard: a private subject vs a caller with no active org.
    assert can_read_subject(private, "someone_else", None) is False


def test_can_write_subject_owner_and_org_teacher_only():
    from app.modules.subjects.service import can_write_subject

    org_subject = _subject("teacher", ORG_O)
    owner_ctx = OrgContext(org_id=ORG_O, org_role=_ROLE_ADMIN)
    teacher_ctx = OrgContext(org_id=ORG_O, org_role=_ROLE_ADMIN)
    student_ctx = OrgContext(org_id=ORG_O, org_role=_ROLE_MEMBER)
    other_org_teacher_ctx = OrgContext(org_id=ORG_O2, org_role=_ROLE_ADMIN)

    assert can_write_subject(org_subject, "teacher", owner_ctx) is True  # owner
    assert can_write_subject(org_subject, "co_teacher", teacher_ctx) is True  # org teacher
    assert can_write_subject(org_subject, "student", student_ctx) is False  # member
    assert can_write_subject(org_subject, "t2", other_org_teacher_ctx) is False  # wrong org

    # Bare (unprefixed) role slug — the runtime-confirmed shape — must grant the
    # same write access as the `org:admin` form above.
    bare_teacher_ctx = OrgContext(org_id=ORG_O, org_role=_ROLE_ADMIN_BARE)
    assert can_write_subject(org_subject, "co_teacher2", bare_teacher_ctx) is True


def test_can_write_subject_private_only_owner():
    from app.modules.subjects.service import can_write_subject

    private = _subject("owner", None)
    assert can_write_subject(private, "owner", OrgContext()) is True
    assert (
        can_write_subject(private, "intruder", OrgContext(org_id=ORG_O, org_role=_ROLE_ADMIN))
        is False
    )
