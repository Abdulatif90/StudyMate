"""Tests for the quiz module — router + service, against an in-memory SQLite DB.
Mirrors tests/test_documents.py's isolation pattern (per-test dependency overrides).

Quiz generation (the Claude tool-use call) is mocked at the service boundary
(`generate_quiz_questions`) so the default suite never touches the network — the real
tool-use call is unit-tested in test_quiz_generation.py, and exercised end-to-end by
the `live` test at the bottom (real Neon + Cohere + Claude). Chunks are inserted
directly (no R2/Inngest needed) since quiz generation only reads chunk text.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core import r2_client
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.documents.embedding import EMBEDDING_DIM
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.quiz import service as quiz_service
from app.modules.quiz.generation import GeneratedQuestion, QuizGenerationError

_TEST_USER = "user_test_123"
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
        options=["Melanin", "Hemoglobin", "Chlorophyll", "Keratin"],
        correct_index=2,
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
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    yield
    del app.dependency_overrides[get_session]
    del app.dependency_overrides[get_current_user_id]
    SQLModel.metadata.drop_all(_engine)


@pytest.fixture(autouse=True)
def _mock_generation(request, monkeypatch):
    """Deterministic stand-in for Claude tool-use quiz generation — autouse so no test
    here makes a network call. Skipped for `@pytest.mark.live` tests, which want the
    real generation path."""
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(
        quiz_service,
        "generate_quiz_questions",
        lambda excerpts, num_questions, language=None: _FAKE_QUESTIONS,
    )


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _create_subject(name: str = "Biology") -> str:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _seed_chunks(owner_id: str, subject_id: str, texts: list[str]) -> None:
    """Insert a document + its chunks straight into the DB — quiz generation only reads
    chunk text, so this skips the whole R2/Inngest/Cohere ingest path."""
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


# --- Generate (POST /subjects/{subject_id}/quizzes) -------------------------


def test_generate_quiz_creates_quiz_with_questions():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Photosynthesis converts sunlight into energy."])

    response = client.post(f"/subjects/{subject_id}/quizzes", json={"num_questions": 2})

    assert response.status_code == 201
    body = response.json()
    assert body["subject_id"] == subject_id
    assert "owner_id" not in body
    assert len(body["questions"]) == 2

    first = body["questions"][0]
    assert first["question"] == _FAKE_QUESTIONS[0].question
    assert first["options"] == _FAKE_QUESTIONS[0].options
    assert first["correct_index"] == 1
    assert first["explanation"] == _FAKE_QUESTIONS[0].explanation
    assert first["order"] == 0
    assert "owner_id" not in first
    # questions come back in generation order
    assert [q["order"] for q in body["questions"]] == [0, 1]


def test_generate_quiz_persists_and_is_fetchable():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Some material."])

    quiz_id = client.post(f"/subjects/{subject_id}/quizzes", json={}).json()["id"]

    fetched = client.get(f"/subjects/{subject_id}/quizzes/{quiz_id}")
    assert fetched.status_code == 200
    assert len(fetched.json()["questions"]) == 2


def test_generate_quiz_returns_404_for_missing_subject():
    response = client.post(f"/subjects/{_MISSING_ID}/quizzes", json={})
    assert response.status_code == 404


def test_generate_quiz_returns_404_for_another_owners_subject():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.post(f"/subjects/{subject_id}/quizzes", json={})
    assert response.status_code == 404


def test_generate_quiz_returns_422_when_subject_has_no_material():
    subject_id = _create_subject()  # no chunks seeded

    response = client.post(f"/subjects/{subject_id}/quizzes", json={})
    assert response.status_code == 422


def test_generate_quiz_returns_502_on_generation_failure(monkeypatch):
    def _raise(excerpts, num_questions, language=None):
        raise QuizGenerationError("Claude is unavailable")

    monkeypatch.setattr(quiz_service, "generate_quiz_questions", _raise)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])

    response = client.post(f"/subjects/{subject_id}/quizzes", json={})
    assert response.status_code == 502


def test_generate_quiz_persists_nothing_on_generation_failure(monkeypatch):
    def _raise(excerpts, num_questions, language=None):
        raise QuizGenerationError("Claude is unavailable")

    monkeypatch.setattr(quiz_service, "generate_quiz_questions", _raise)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/quizzes", json={})

    # the Quiz row is only added after questions come back, so a generation failure
    # leaves no orphaned empty quiz behind
    assert client.get(f"/subjects/{subject_id}/quizzes").json() == []


def test_generate_quiz_passes_num_questions_through(monkeypatch):
    captured = {}

    def _capture(excerpts, num_questions, language=None):
        captured["n"] = num_questions
        return _FAKE_QUESTIONS

    monkeypatch.setattr(quiz_service, "generate_quiz_questions", _capture)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/quizzes", json={"num_questions": 7})

    assert captured["n"] == 7


def test_generate_quiz_passes_language_through(monkeypatch):
    captured = {}

    def _capture(excerpts, num_questions, language=None):
        captured["language"] = language
        return _FAKE_QUESTIONS

    monkeypatch.setattr(quiz_service, "generate_quiz_questions", _capture)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/quizzes", json={"language": "ko"})

    assert captured["language"] == "ko"


def test_generate_quiz_defaults_language_to_english(monkeypatch):
    captured = {}

    def _capture(excerpts, num_questions, language=None):
        captured["language"] = language
        return _FAKE_QUESTIONS

    monkeypatch.setattr(quiz_service, "generate_quiz_questions", _capture)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/quizzes", json={})

    assert captured["language"] == "en"


def test_generate_quiz_rejects_out_of_bounds_num_questions():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])

    assert (
        client.post(f"/subjects/{subject_id}/quizzes", json={"num_questions": 0}).status_code == 422
    )
    assert (
        client.post(f"/subjects/{subject_id}/quizzes", json={"num_questions": 21}).status_code
        == 422
    )


# --- List / get -------------------------------------------------------------


def test_list_quizzes_returns_them_without_questions():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/quizzes", json={})

    response = client.get(f"/subjects/{subject_id}/quizzes")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert "questions" not in body[0]  # list shape is summary-only
    assert "owner_id" not in body[0]


def test_list_quizzes_is_owner_scoped():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/quizzes", json={})

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    # someone_else doesn't own the subject → 404 (not an empty list)
    assert client.get(f"/subjects/{subject_id}/quizzes").status_code == 404


def test_list_quizzes_returns_404_for_missing_subject():
    assert client.get(f"/subjects/{_MISSING_ID}/quizzes").status_code == 404


def test_get_quiz_returns_404_when_missing():
    subject_id = _create_subject()
    assert client.get(f"/subjects/{subject_id}/quizzes/{_MISSING_ID}").status_code == 404


def test_get_quiz_returns_404_from_a_different_subject():
    subject_a = _create_subject(name="Bio")
    subject_b = _create_subject(name="Chem")
    _seed_chunks(_TEST_USER, subject_a, ["Material."])
    quiz_id = client.post(f"/subjects/{subject_a}/quizzes", json={}).json()["id"]

    # the quiz exists but not under subject_b — must 404, not leak across subjects
    assert client.get(f"/subjects/{subject_b}/quizzes/{quiz_id}").status_code == 404


def test_get_quiz_returns_404_for_another_owner():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    quiz_id = client.post(f"/subjects/{subject_id}/quizzes", json={}).json()["id"]

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    assert client.get(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 404


# --- Delete -----------------------------------------------------------------


def test_delete_quiz_removes_it_and_its_questions():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    quiz_id = client.post(f"/subjects/{subject_id}/quizzes", json={}).json()["id"]

    response = client.delete(f"/subjects/{subject_id}/quizzes/{quiz_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 404
    # questions are gone too (deleted before the parent, flush-ordered)
    with Session(_engine) as session:
        assert quiz_service.list_questions(session, _TEST_USER, uuid.UUID(quiz_id)) == []


def test_delete_quiz_returns_404_when_missing():
    subject_id = _create_subject()
    assert client.delete(f"/subjects/{subject_id}/quizzes/{_MISSING_ID}").status_code == 404


def test_delete_quiz_returns_404_for_another_owner_and_leaves_it_intact():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    quiz_id = client.post(f"/subjects/{subject_id}/quizzes", json={}).json()["id"]

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    assert client.delete(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 404

    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    assert client.get(f"/subjects/{subject_id}/quizzes/{quiz_id}").status_code == 200


def test_delete_quiz_from_a_different_subject_returns_404():
    subject_a = _create_subject(name="Bio")
    subject_b = _create_subject(name="Chem")
    _seed_chunks(_TEST_USER, subject_a, ["Material."])
    quiz_id = client.post(f"/subjects/{subject_a}/quizzes", json={}).json()["id"]

    assert client.delete(f"/subjects/{subject_b}/quizzes/{quiz_id}").status_code == 404
    assert client.get(f"/subjects/{subject_a}/quizzes/{quiz_id}").status_code == 200


# --- Live (real Neon + Cohere + Claude tool-use) ----------------------------


@pytest.fixture(autouse=True)
def _mock_r2(request, monkeypatch):
    """In-memory R2 for the live test's create_document/process_document byte round-trip
    (real Cohere/Claude still run). Offline tests seed chunks directly and never touch
    R2, so this is harmless there."""
    store: dict[str, bytes] = {}

    def put(key, data, content_type):
        store[key] = data

    monkeypatch.setattr(r2_client, "put_object", put)
    monkeypatch.setattr(r2_client, "get_object", lambda key: store[key])
    monkeypatch.setattr(r2_client, "delete_object", lambda key: store.pop(key, None))


_HAS_REAL_DB = bool(get_settings().database_url)


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_REAL_DB, reason="requires DATABASE_URL (real Neon) and a real Claude key"
)
def test_generate_quiz_end_to_end_against_real_neon_cohere_and_claude():
    from app.core.db import get_engine
    from app.modules.documents import service as documents_service
    from app.modules.subjects import service as subjects_service
    from app.modules.subjects.schemas import SubjectCreate

    engine = get_engine()
    owner_id = "live_smoke_test_user_quiz"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Quiz Smoke Test")
        )
        document = documents_service.create_document(
            session,
            owner_id,
            subject.id,
            filename="photosynthesis.txt",
            content_type="text/plain",
            raw=(
                b"Photosynthesis converts sunlight into chemical energy in plant "
                b"chloroplasts. Chlorophyll absorbs light, water is split to release "
                b"oxygen, and carbon dioxide is fixed into glucose."
            ),
        )
        documents_service.process_document(session, owner_id, document.id)

        quiz = None
        try:
            quiz = quiz_service.generate_quiz(session, owner_id, subject.id, num_questions=3)
            questions = quiz_service.list_questions(session, owner_id, quiz.id)

            assert len(questions) >= 1
            for question in questions:
                assert question.question.strip()
                assert len(question.options) >= 2
                assert 0 <= question.correct_index < len(question.options)
        finally:
            if quiz is not None:
                for question in quiz_service.list_questions(session, owner_id, quiz.id):
                    session.delete(question)
                session.commit()
                session.delete(quiz)
            for chunk in documents_service.list_chunks(session, owner_id, document.id):
                session.delete(chunk)
            session.commit()
            session.delete(document)
            session.delete(subject)
            session.commit()
