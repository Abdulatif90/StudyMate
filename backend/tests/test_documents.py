"""Tests for the documents module — router + service, against an in-memory SQLite DB.

Mirrors tests/test_subjects.py's isolation pattern (see there for why overrides are
scoped per-test rather than at import time).

Processing is async now: upload validates + inserts a `pending` row and emits an
Inngest event, then a background job (service.process_document) parses/chunks/embeds
and resolves the document to ready/failed. Tests exercise both halves separately —
the Inngest event-send is mocked (`_mock_inngest`, autouse — no network) and the job
is driven by calling `process_document` directly (`_process`). Cohere is mocked
everywhere too (`_mock_cohere`, autouse).
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


@pytest.fixture(autouse=True)
def _mock_inngest(monkeypatch):
    """Replace the Inngest event-send with a no-op Mock so upload tests never touch
    the network. Returned so tests can assert the upload path enqueued processing."""
    enqueue = Mock()
    monkeypatch.setattr(documents_service, "enqueue_document_processing", enqueue)
    return enqueue


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _create_subject(name: str = "Biology") -> str:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _txt_file(content: bytes = b"hello world"):
    return {"file": ("notes.txt", io.BytesIO(content), "text/plain")}


def _process(owner_id: str, document_id: str):
    """Drive the async job synchronously: what the Inngest function does when the
    `document/uploaded` event fires."""
    with Session(_engine) as session:
        document = documents_service.process_document(session, owner_id, uuid.UUID(document_id))
        session.expunge_all()
        return document


def _chunks(owner_id: str, document_id: str) -> list[documents_service.DocumentChunk]:
    """Chunks have no HTTP endpoint yet, so tests read them straight from the DB."""
    with Session(_engine) as session:
        chunks = documents_service.list_chunks(session, owner_id, uuid.UUID(document_id))
        session.expunge_all()  # keep the rows usable after the session closes
        return chunks


def _chunk_texts(owner_id: str, document_id: str) -> list[str]:
    return [chunk.text for chunk in _chunks(owner_id, document_id)]


# --- Upload (sync request path — returns pending, enqueues the job) ---------


def test_upload_returns_pending_and_enqueues_processing(_mock_inngest):
    subject_id = _create_subject()

    response = client.post(f"/subjects/{subject_id}/documents", files=_txt_file())

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["status"] == "pending"
    assert "owner_id" not in body
    # the upload path emits the event exactly once, after the row is committed
    _mock_inngest.assert_called_once()


def test_upload_does_no_processing_on_the_request_path():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    # nothing parsed/embedded yet — that's the whole point of moving it off-request
    assert created["status"] == "pending"
    assert _chunk_texts(_TEST_USER, created["id"]) == []


def test_upload_and_list_documents():
    subject_id = _create_subject()

    client.post(f"/subjects/{subject_id}/documents", files=_txt_file())
    response = client.get(f"/subjects/{subject_id}/documents")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_document_returns_it():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    response = client.get(f"/subjects/{subject_id}/documents/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_upload_returns_404_for_missing_subject(_mock_inngest):
    response = client.post(f"/subjects/{_MISSING_ID}/documents", files=_txt_file())
    assert response.status_code == 404
    _mock_inngest.assert_not_called()  # nothing to process — never enqueues


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


def test_upload_rejects_unsupported_content_type(_mock_inngest):
    subject_id = _create_subject()
    files = {"file": ("image.png", io.BytesIO(b"fake png bytes"), "image/png")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 415
    _mock_inngest.assert_not_called()


def test_upload_rejects_oversize_file(_mock_inngest):
    subject_id = _create_subject()
    big_content = b"x" * (21 * 1024 * 1024)  # over the 20 MB limit
    files = {"file": ("big.txt", io.BytesIO(big_content), "text/plain")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 413
    _mock_inngest.assert_not_called()


# --- Processing (the async job — service.process_document) ------------------


def test_process_resolves_pending_to_ready_with_chunks():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    document = _process(_TEST_USER, created["id"])

    assert document.status.value == "ready"
    assert _chunk_texts(_TEST_USER, created["id"]) == ["hello world"]


def test_process_marks_unparseable_pdf_failed_with_no_chunks():
    subject_id = _create_subject()
    files = {"file": ("broken.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()
    assert created["status"] == "pending"

    document = _process(_TEST_USER, created["id"])

    assert document.status.value == "failed"
    assert _chunk_texts(_TEST_USER, created["id"]) == []


def test_process_marks_failed_when_embedding_fails(monkeypatch):
    def _raise_embedding_error(texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("Cohere is unavailable")

    monkeypatch.setattr(documents_service, "embed_texts", _raise_embedding_error)

    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    document = _process(_TEST_USER, created["id"])

    assert document.status.value == "failed"
    assert _chunks(_TEST_USER, created["id"]) == []


def test_process_creates_ordered_chunks_for_long_text():
    subject_id = _create_subject()
    long_text = " ".join(f"This is sentence number {i}." for i in range(200)).encode()
    files = {"file": ("long.txt", io.BytesIO(long_text), "text/plain")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    _process(_TEST_USER, created["id"])

    chunks = _chunk_texts(_TEST_USER, created["id"])
    assert len(chunks) > 1
    positions = [long_text.decode().index(chunk) for chunk in chunks]
    assert positions == sorted(positions)


def test_process_stores_an_embedding_per_chunk():
    subject_id = _create_subject()
    long_text = " ".join(f"This is sentence number {i}." for i in range(200)).encode()
    files = {"file": ("long.txt", io.BytesIO(long_text), "text/plain")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    _process(_TEST_USER, created["id"])

    chunks = _chunks(_TEST_USER, created["id"])
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == EMBEDDING_DIM
        # matches _fake_embed_texts' deterministic scheme: first component = len(text)
        assert chunk.embedding[0] == float(len(chunk.text))


def test_process_chunks_are_scoped_to_owner():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    _process(_TEST_USER, created["id"])

    assert len(_chunk_texts(_TEST_USER, created["id"])) == 1
    assert _chunk_texts("someone_else", created["id"]) == []


def test_process_whitespace_only_text_file_is_ready_with_no_chunks():
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file(b"   \n  ")).json()

    document = _process(_TEST_USER, created["id"])

    assert document.status.value == "ready"  # parses fine, just has no real content
    assert _chunk_texts(_TEST_USER, created["id"]) == []


def test_process_empty_document_embeds_nothing(monkeypatch):
    embed_spy = Mock(side_effect=_fake_embed_texts)
    monkeypatch.setattr(documents_service, "embed_texts", embed_spy)

    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file(b"   \n  ")).json()

    _process(_TEST_USER, created["id"])

    assert _chunks(_TEST_USER, created["id"]) == []
    # process_document doesn't special-case an empty chunk list — it still calls
    # embed_texts([]), relying on embed_texts' own short-circuit (verified with the
    # real Cohere client mocked in test_embedding.py) to avoid the network call.
    embed_spy.assert_called_once_with([])


def test_process_is_idempotent_after_success():
    """A retry after the job already completed is a no-op — raw_content was cleared,
    so reprocessing neither errors nor duplicates chunks."""
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    _process(_TEST_USER, created["id"])
    assert len(_chunk_texts(_TEST_USER, created["id"])) == 1

    # second run (Inngest retry after a successful-but-unacked run)
    document = _process(_TEST_USER, created["id"])
    assert document.status.value == "ready"
    assert len(_chunk_texts(_TEST_USER, created["id"])) == 1  # not doubled


def test_process_retry_reprocesses_without_duplicate_chunks():
    """A retry after a *partial* attempt (raw_content still present) deletes the prior
    attempt's chunks before re-inserting, so it can't accumulate duplicates."""
    subject_id = _create_subject()
    long_text = " ".join(f"This is sentence number {i}." for i in range(200)).encode()
    files = {"file": ("long.txt", io.BytesIO(long_text), "text/plain")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    _process(_TEST_USER, created["id"])
    first_count = len(_chunk_texts(_TEST_USER, created["id"]))
    assert first_count > 1

    # Simulate a retry where the previous attempt didn't clear raw_content (e.g. it
    # raised after inserting chunks): restore the bytes, then reprocess.
    with Session(_engine) as session:
        doc = documents_service.get_document_by_id(session, _TEST_USER, uuid.UUID(created["id"]))
        doc.raw_content = long_text
        session.add(doc)
        session.commit()

    _process(_TEST_USER, created["id"])
    assert len(_chunk_texts(_TEST_USER, created["id"])) == first_count  # deleted-then-reinserted


def test_process_missing_document_is_a_noop():
    # e.g. the document was deleted between upload and the job running
    assert _process(_TEST_USER, _MISSING_ID) is None
