"""Cross-tenant isolation tests for quizzes over org-owned (read-shared) subjects —
Phase 5 increment 2b (the quiz read-through). Mirrors test_org_flashcards.py: a bug here
would let one student read another student's private quiz, or generate/read across org
boundaries. Quizzes have no per-user state (no SM-2), so reading returns the same content
to every reader — but only the SUBJECT OWNER's quizzes are shared, never another
student's.

Same offline, isolated-SQLite pattern: `app.dependency_overrides` swaps `get_session`,
`get_current_user_id`, and `get_org_context` per test; identity is switched mid-test via
`_act_as`. Quiz generation (the Claude tool-use call) is stubbed so nothing hits the
network; chunks are inserted directly (generation only reads chunk text).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.documents.embedding import EMBEDDING_DIM
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.quiz import service as quiz_service
from app.modules.quiz.generation import GeneratedQuestion
from app.modules.quiz.models import Quiz

# --- Identities -------------------------------------------------------------
# Org O: a teacher (admin) who owns the shared subject + its quizzes, plus two plain
# student members. Org O2: a separate org whose student must never see O's content.
TEACHER = "user_teacher_O"
STUDENT = "user_student_O"
STUDENT2 = "user_student2_O"
OTHER_ORG_STUDENT = "user_student_O2"
LONER = "user_no_org"  # signed in, no active organization

ORG_O = "org_O"
ORG_O2 = "org_O2"

_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)

_FAKE_QUESTIONS = [
    GeneratedQuestion(
        question="What does photosynthesis convert sunlight into?",
        options=["Water", "Chemical energy", "Nitrogen"],
        correct_index=1,
        explanation="It converts sunlight into chemical energy.",
    ),
    GeneratedQuestion(
        question="What pigment absorbs light?",
        options=["Melanin", "Chlorophyll", "Keratin"],
        correct_index=1,
        explanation="Chlorophyll absorbs light.",
    ),
]


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


@pytest.fixture(autouse=True)
def _mock_generation(monkeypatch):
    """Deterministic stand-in for Claude tool-use quiz generation — no network."""
    monkeypatch.setattr(
        quiz_service,
        "generate_quiz_questions",
        lambda excerpts, num_questions, language=None: _FAKE_QUESTIONS,
    )


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


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


def _seed_chunks(owner_id: str, subject_id: str, texts: list[str]) -> None:
    with Session(_engine) as session:
        document = Document(
            subject_id=uuid.UUID(subject_id),
            owner_id=owner_id,
            filename="notes.txt",
            content_type="text/plain",
            status=DocumentStatus.READY,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        for index, text in enumerate(texts):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    subject_id=uuid.UUID(subject_id),
                    owner_id=owner_id,
                    chunk_index=index,
                    text=text,
                    embedding=[0.1] * EMBEDDING_DIM,
                )
            )
        session.commit()


def _generate(subject_id: str) -> dict:
    response = client.post(f"/subjects/{subject_id}/quizzes", json={"num_questions": 2})
    assert response.status_code == 201, response.text
    return response.json()


def _quiz_owner(quiz_id: str) -> str:
    with Session(_engine) as session:
        return session.get(Quiz, uuid.UUID(quiz_id)).owner_id


# ---------------------------------------------------------------------------
# Generation over a shared subject → quiz owned by the caller.
# ---------------------------------------------------------------------------


def test_member_generates_quiz_over_teacher_org_subject_owned_by_member():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Photosynthesis converts sunlight into energy."])

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    quiz = _generate(subject_id)

    assert len(quiz["questions"]) == 2  # reader-variant sampling saw the TEACHER's chunks
    assert _quiz_owner(quiz["id"]) == STUDENT  # per-student ownership


def test_loner_with_no_active_org_cannot_generate_over_org_subject():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(LONER, None, None)
    assert client.post(f"/subjects/{subject_id}/quizzes", json={}).status_code == 404


def test_member_of_different_org_cannot_generate_over_org_subject():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.post(f"/subjects/{subject_id}/quizzes", json={}).status_code == 404


# ---------------------------------------------------------------------------
# Reading over a shared subject: own + teacher's quizzes, never another student's.
# ---------------------------------------------------------------------------


def test_member_can_read_teacher_shared_quiz_and_its_questions():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    teacher_quiz = _generate(subject_id)

    # A student member of the org reads the teacher's shared quiz + its questions.
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    listed = client.get(f"/subjects/{subject_id}/quizzes")
    assert listed.status_code == 200
    assert teacher_quiz["id"] in {q["id"] for q in listed.json()}

    got = client.get(f"/subjects/{subject_id}/quizzes/{teacher_quiz['id']}")
    assert got.status_code == 200
    assert len(got.json()["questions"]) == 2  # the teacher-owned questions are returned


def test_member_list_includes_own_and_teacher_quizzes_not_other_students():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    teacher_quiz = _generate(subject_id)["id"]

    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    student2_quiz = _generate(subject_id)["id"]

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    student_quiz = _generate(subject_id)["id"]
    listed = {q["id"] for q in client.get(f"/subjects/{subject_id}/quizzes").json()}

    assert student_quiz in listed  # own
    assert teacher_quiz in listed  # the shared (owner's) set
    assert student2_quiz not in listed  # NOT another student's private quiz


def test_teacher_list_shows_only_own_quizzes_over_own_shared_subject():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    teacher_quiz = _generate(subject_id)["id"]

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    student_quiz = _generate(subject_id)["id"]

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    listed = {q["id"] for q in client.get(f"/subjects/{subject_id}/quizzes").json()}
    assert listed == {teacher_quiz}
    assert student_quiz not in listed


def test_member_cannot_read_another_students_private_quiz():
    # THE leak-regression test (mirrors flashcard's cross-student review guard): a
    # student's own quiz over a shared subject is PRIVATE (owner_id-scoped) — only the
    # subject owner's quizzes are shared. Student B, knowing A's quiz id, must get 404 on
    # both the get and the list.
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    private_quiz = _generate(subject_id)["id"]
    assert _quiz_owner(private_quiz) == STUDENT

    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    assert client.get(f"/subjects/{subject_id}/quizzes/{private_quiz}").status_code == 404
    listed = {q["id"] for q in client.get(f"/subjects/{subject_id}/quizzes").json()}
    assert private_quiz not in listed


def test_member_of_different_org_cannot_list_or_get_org_quiz():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    quiz_id = _generate(subject_id)["id"]

    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.get(f"/subjects/{subject_id}/quizzes").status_code == 404
    assert client.get(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 404


# ---------------------------------------------------------------------------
# Delete: owner-only. A student can't delete a teacher's shared quiz.
# ---------------------------------------------------------------------------


def test_member_cannot_delete_teacher_shared_quiz():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    quiz_id = _generate(subject_id)["id"]

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.delete(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 404
    with Session(_engine) as session:
        assert session.get(Quiz, uuid.UUID(quiz_id)) is not None  # still there


def test_owner_can_delete_own_shared_quiz():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    quiz_id = _generate(subject_id)["id"]

    assert client.delete(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 204
    with Session(_engine) as session:
        assert session.get(Quiz, uuid.UUID(quiz_id)) is None
