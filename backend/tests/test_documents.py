"""Tests for the documents module — router + service, against an in-memory SQLite DB.

Mirrors tests/test_subjects.py's isolation pattern (see there for why overrides are
scoped per-test rather than at import time). Text-only external deps, no R2/Inngest:
uploads are parsed/chunked/embedded synchronously in-request. Cohere is mocked in every
test (`_mock_cohere`, autouse) — no test in this file makes a real network call.
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.main import app
from app.modules.documents import service as documents_service
from app.modules.documents.embedding import EMBEDDING_DIM, EmbeddingError

_TEST_USER = "user_test_123"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _get_test_session():
    with Session(_engine) as session:
        yield session


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    """Deterministic stand-in for Cohere — same shape (1024-dim per input text), no
    network. Encodes each text's length into the first component so tests can tell
    which vector came from which chunk without needing real semantic embeddings.
    """
    return [[float(len(text))] + [0.0] * (EMBEDDING_DIM - 1) for text in texts]


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


def _txt_file(content: bytes = b"hello world"):
    return {"file": ("notes.txt", io.BytesIO(content), "text/plain")}


def _chunks(owner_id: str, document_id: str) -> list[documents_service.DocumentChunk]:
    """Chunks have no HTTP endpoint yet, so tests read them straight from the DB."""
    with Session(_engine) as session:
        chunks = documents_service.list_chunks(session, owner_id, uuid.UUID(document_id))
        session.expunge_all()  # keep the rows usable after the session closes
        return chunks


def _chunk_texts(owner_id: str, document_id: str) -> list[str]:
    return [chunk.text for chunk in _chunks(owner_id, document_id)]


def test_upload_and_list_documents():
    subject_id = _create_subject()

    response = client.post(f"/subjects/{subject_id}/documents", files=_txt_file())
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["status"] == "ready"
    assert "owner_id" not in body

    response = client.get(f"/subjects/{subject_id}/documents")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_document_returns_it():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    response = client.get(f"/subjects/{subject_id}/documents/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_upload_returns_404_for_missing_subject():
    response = client.post(f"/subjects/{_MISSING_ID}/documents", files=_txt_file())
    assert response.status_code == 404


def test_list_returns_404_for_missing_subject():
    response = client.get(f"/subjects/{_MISSING_ID}/documents")
    assert response.status_code == 404


def test_get_document_returns_404_when_missing():
    subject_id = _create_subject()
    response = client.get(f"/subjects/{subject_id}/documents/{_MISSING_ID}")
    assert response.status_code == 404


def test_documents_are_scoped_to_owner():
    subject_id = _create_subject()
    client.post(f"/subjects/{subject_id}/documents", files=_txt_file())

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    # someone_else doesn't own the subject either, so it's a 404, not an empty list.
    response = client.get(f"/subjects/{subject_id}/documents")
    assert response.status_code == 404


def test_upload_rejects_unsupported_content_type():
    subject_id = _create_subject()
    files = {"file": ("image.png", io.BytesIO(b"fake png bytes"), "image/png")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 415


def test_upload_rejects_oversize_file():
    subject_id = _create_subject()
    big_content = b"x" * (21 * 1024 * 1024)  # over the 20 MB limit
    files = {"file": ("big.txt", io.BytesIO(big_content), "text/plain")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 413


def test_upload_marks_unparseable_pdf_as_failed():
    subject_id = _create_subject()
    files = {"file": ("broken.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 201
    assert response.json()["status"] == "failed"


def test_upload_creates_a_single_chunk_for_short_text():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    assert _chunk_texts(_TEST_USER, created["id"]) == ["hello world"]


def test_upload_creates_ordered_chunks_for_long_text():
    subject_id = _create_subject()
    long_text = " ".join(f"This is sentence number {i}." for i in range(200)).encode()
    files = {"file": ("long.txt", io.BytesIO(long_text), "text/plain")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    chunks = _chunk_texts(_TEST_USER, created["id"])
    assert len(chunks) > 1
    # list_chunks orders by chunk_index — confirm that matches source order too
    positions = [long_text.decode().index(chunk) for chunk in chunks]
    assert positions == sorted(positions)


def test_chunks_are_scoped_to_owner():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    assert len(_chunk_texts(_TEST_USER, created["id"])) == 1
    assert _chunk_texts("someone_else", created["id"]) == []


def test_unparseable_pdf_creates_no_chunks():
    subject_id = _create_subject()
    files = {"file": ("broken.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    assert created["status"] == "failed"
    assert _chunk_texts(_TEST_USER, created["id"]) == []


def test_whitespace_only_text_file_creates_no_chunks():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file(b"   \n  ")).json()

    assert created["status"] == "ready"  # parses fine, just has no real content
    assert _chunk_texts(_TEST_USER, created["id"]) == []


def test_upload_stores_an_embedding_per_chunk():
    subject_id = _create_subject()
    long_text = " ".join(f"This is sentence number {i}." for i in range(200)).encode()
    files = {"file": ("long.txt", io.BytesIO(long_text), "text/plain")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    chunks = _chunks(_TEST_USER, created["id"])
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == EMBEDDING_DIM
        # matches _fake_embed_texts' deterministic scheme: first component = len(text)
        assert chunk.embedding[0] == float(len(chunk.text))


def test_embeddings_are_scoped_to_owner():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    own_chunks = _chunks(_TEST_USER, created["id"])
    assert len(own_chunks) == 1
    assert own_chunks[0].embedding is not None

    assert _chunks("someone_else", created["id"]) == []


def test_empty_document_embeds_nothing(monkeypatch):
    embed_spy = Mock(side_effect=_fake_embed_texts)
    monkeypatch.setattr(documents_service, "embed_texts", embed_spy)

    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file(b"   \n  ")).json()

    assert created["status"] == "ready"
    assert _chunks(_TEST_USER, created["id"]) == []
    # service.py doesn't special-case an empty chunk list itself — it still calls
    # embed_texts([]), relying on embed_texts' own short-circuit (verified directly,
    # with the real Cohere client mocked out, in test_embedding.py) to avoid the
    # network call. This confirms that wiring holds at the integration level too.
    embed_spy.assert_called_once_with([])


def test_upload_marks_document_failed_when_embedding_fails(monkeypatch):
    def _raise_embedding_error(texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("Cohere is unavailable")

    monkeypatch.setattr(documents_service, "embed_texts", _raise_embedding_error)

    subject_id = _create_subject()
    response = client.post(f"/subjects/{subject_id}/documents", files=_txt_file())

    assert response.status_code == 201  # the request itself still succeeds
    body = response.json()
    assert body["status"] == "failed"
    assert _chunks(_TEST_USER, body["id"]) == []
