"""Tests for the Ask endpoint (app.modules.ask) — router + service, against an
in-memory SQLite DB. Mirrors tests/test_documents.py's isolation pattern.

search_chunks skips its Cohere call entirely off Postgres (see documents/service.py),
so on SQLite only document upload (which calls embed_texts) needs Cohere mocked —
the ask flow itself only needs Claude (ask_claude) mocked. Real end-to-end behavior
(real retrieval ranking + real Claude generation) is covered by the `live` test at
the bottom, against real Neon — skipped by default, run with `pytest -m live`.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.ask import service as ask_service
from app.modules.documents import service as documents_service
from app.modules.documents.embedding import EMBEDDING_DIM

_TEST_USER = "user_test_123"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _get_test_session():
    with Session(_engine) as session:
        yield session


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    return [[0.1] * EMBEDDING_DIM for _ in texts]


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
def _mock_cohere(monkeypatch):
    monkeypatch.setattr(documents_service, "embed_texts", _fake_embed_texts)


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _create_subject(name: str = "Biology") -> str:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _upload_txt(
    subject_id: str, content: bytes = b"Photosynthesis converts sunlight into energy."
) -> dict:
    files = {"file": ("notes.txt", io.BytesIO(content), "text/plain")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 201
    return response.json()


def test_ask_returns_answer_and_sources(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)

    mock_ask_claude = MagicMock(return_value="Plants use sunlight via photosynthesis.")
    monkeypatch.setattr(ask_service, "ask_claude", mock_ask_claude)

    response = client.post(
        f"/subjects/{subject_id}/ask", json={"question": "How do plants use sunlight?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Plants use sunlight via photosynthesis."
    assert len(body["sources"]) == 1
    assert body["sources"][0]["filename"] == "notes.txt"
    assert body["sources"][0]["chunk_index"] == 0
    assert "Photosynthesis" in body["sources"][0]["text"]

    # confirm the retrieved chunk's context was actually passed to Claude
    question_arg, chunks_arg = mock_ask_claude.call_args[0]
    assert question_arg == "How do plants use sunlight?"
    assert chunks_arg[0]["filename"] == "notes.txt"
    assert "Photosynthesis" in chunks_arg[0]["text"]


def test_ask_returns_404_for_missing_subject():
    response = client.post(f"/subjects/{_MISSING_ID}/ask", json={"question": "anything?"})
    assert response.status_code == 404


def test_ask_returns_404_for_another_owners_subject():
    subject_id = _create_subject()
    _upload_txt(subject_id)

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})
    assert response.status_code == 404


def test_ask_with_no_documents_returns_graceful_no_material_message(monkeypatch):
    subject_id = _create_subject()  # no documents uploaded — nothing to retrieve

    mock_ask_claude = MagicMock()
    monkeypatch.setattr(ask_service, "ask_claude", mock_ask_claude)

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert "couldn't find" in body["answer"].lower()
    mock_ask_claude.assert_not_called()  # nothing to ground on — never even calls Claude


def test_ask_gracefully_handles_llm_failure(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)

    monkeypatch.setattr(
        ask_service, "ask_claude", MagicMock(side_effect=ask_service.LLMError("boom"))
    )

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert "try again" in body["answer"].lower()


_HAS_REAL_DB = bool(get_settings().database_url)


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_REAL_DB, reason="requires DATABASE_URL (real Neon) and a real Claude key"
)
def test_ask_end_to_end_against_real_neon_and_claude():
    from app.core.db import get_engine
    from app.modules.ask.service import ask_question
    from app.modules.subjects import service as subjects_service
    from app.modules.subjects.schemas import SubjectCreate

    engine = get_engine()
    owner_id = "live_smoke_test_user"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Ask Smoke Test")
        )
        document = documents_service.create_document(
            session,
            owner_id,
            subject.id,
            filename="photosynthesis.txt",
            content_type="text/plain",
            raw=(
                b"Photosynthesis converts sunlight into chemical energy in plant "
                b"chloroplasts. Chlorophyll absorbs sunlight."
            ),
        )

        try:
            response = ask_question(session, owner_id, subject.id, "How do plants use sunlight?")

            assert response.sources, "expected at least one source chunk"
            assert "photosynthesis.txt" in [source.filename for source in response.sources]
            assert len(response.answer) > 0
            assert "n't find" not in response.answer.lower()  # actually grounded, not a refusal
        finally:
            for chunk in documents_service.list_chunks(session, owner_id, document.id):
                session.delete(chunk)
            session.commit()
            session.delete(document)
            session.delete(subject)
            session.commit()
