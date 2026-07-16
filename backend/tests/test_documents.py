"""Tests for the documents module — router + service, against an in-memory SQLite DB.

Mirrors tests/test_subjects.py's isolation pattern (see there for why overrides are
scoped per-test rather than at import time).

Processing is async now: upload validates + uploads the bytes to R2 + inserts a
`pending` row, then a background job (service.process_document) fetches from R2 and
parses/chunks/embeds, resolving the document to ready/failed. Tests exercise both
halves separately — Inngest is mocked (`_mock_inngest`), R2 is an in-memory fake
(`_mock_r2`), Cohere is mocked (`_mock_cohere`) — all autouse, so no test here makes
a network call. The job is driven by calling `process_document` directly (`_process`).
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core import r2_client
from app.core.auth import get_current_user_id
from app.core.config import get_settings
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


@pytest.fixture(autouse=True)
def _mock_r2(request, monkeypatch):
    """In-memory stand-in for R2 — put/get/delete against a dict, no network. Returned
    so tests can assert the upload path actually stored the bytes.

    Skipped for `@pytest.mark.live` tests — those deliberately want the real
    `r2_client` functions so they can round-trip through the real bucket.
    """
    if request.node.get_closest_marker("live"):
        yield None
        return

    store: dict[str, bytes] = {}

    def put(key, data, content_type):
        store[key] = data

    monkeypatch.setattr(r2_client, "put_object", put)
    monkeypatch.setattr(r2_client, "get_object", lambda key: store[key])
    monkeypatch.setattr(r2_client, "delete_object", lambda key: store.pop(key, None))
    yield store
    return store


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


def test_upload_stores_the_file_in_r2_under_an_owner_scoped_key(_mock_r2):
    subject_id = _create_subject()

    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file(b"hi")).json()

    # exactly one object stored, keyed by {owner}/{document_id}/{filename}
    assert list(_mock_r2) == [f"{_TEST_USER}/{created['id']}/notes.txt"]
    assert _mock_r2[f"{_TEST_USER}/{created['id']}/notes.txt"] == b"hi"


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


def test_process_run_twice_does_not_duplicate_chunks():
    """Re-running the job (Inngest retry) re-fetches from R2 and deletes the prior
    attempt's chunks before re-inserting, so chunks never accumulate — the byte source
    (R2) is unchanged, so this holds whether the last attempt fully or partly ran."""
    subject_id = _create_subject()
    long_text = " ".join(f"This is sentence number {i}." for i in range(200)).encode()
    files = {"file": ("long.txt", io.BytesIO(long_text), "text/plain")}
    created = client.post(f"/subjects/{subject_id}/documents", files=files).json()

    _process(_TEST_USER, created["id"])
    first_count = len(_chunk_texts(_TEST_USER, created["id"]))
    assert first_count > 1

    document = _process(_TEST_USER, created["id"])  # second run
    assert document.status.value == "ready"
    assert len(_chunk_texts(_TEST_USER, created["id"])) == first_count  # not doubled


def test_process_keeps_the_r2_object_after_processing(_mock_r2):
    """R2 is the file store now (not a temp stash) — the object stays after processing,
    so the document can be re-processed."""
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file(b"keep me")).json()

    key = f"{_TEST_USER}/{created['id']}/notes.txt"
    assert key in _mock_r2
    _process(_TEST_USER, created["id"])
    assert key in _mock_r2  # still there after processing


def test_process_missing_document_is_a_noop():
    # e.g. the document was deleted between upload and the job running
    assert _process(_TEST_USER, _MISSING_ID) is None


# --- Delete (DELETE /subjects/{subject_id}/documents/{document_id}) ---------


def test_delete_removes_the_document_its_chunks_and_its_r2_object(_mock_r2):
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()
    _process(_TEST_USER, created["id"])
    key = f"{_TEST_USER}/{created['id']}/notes.txt"
    assert key in _mock_r2
    assert len(_chunk_texts(_TEST_USER, created["id"])) == 1

    response = client.delete(f"/subjects/{subject_id}/documents/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/subjects/{subject_id}/documents/{created['id']}").status_code == 404
    assert _chunk_texts(_TEST_USER, created["id"]) == []
    assert key not in _mock_r2


def test_delete_a_pending_document_with_no_chunks_yet():
    # not processed yet — no chunks exist, must still delete cleanly
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()
    assert created["status"] == "pending"

    response = client.delete(f"/subjects/{subject_id}/documents/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/subjects/{subject_id}/documents/{created['id']}").status_code == 404


def test_delete_returns_404_when_document_missing():
    subject_id = _create_subject()
    response = client.delete(f"/subjects/{subject_id}/documents/{_MISSING_ID}")
    assert response.status_code == 404


def test_delete_returns_404_for_missing_subject():
    response = client.delete(f"/subjects/{_MISSING_ID}/documents/{_MISSING_ID}")
    assert response.status_code == 404


def test_delete_returns_404_for_another_owners_document_and_leaves_it_untouched(_mock_r2):
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()
    _process(_TEST_USER, created["id"])
    key = f"{_TEST_USER}/{created['id']}/notes.txt"

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.delete(f"/subjects/{subject_id}/documents/{created['id']}")
    assert response.status_code == 404

    # untouched: still fetchable (as the real owner), chunks intact, R2 object intact
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    assert client.get(f"/subjects/{subject_id}/documents/{created['id']}").status_code == 200
    assert len(_chunk_texts(_TEST_USER, created["id"])) == 1
    assert key in _mock_r2


def test_delete_from_a_different_subject_returns_404():
    subject_a = _create_subject(name="Bio")
    subject_b = _create_subject(name="Chem")
    created = client.post(f"/subjects/{subject_a}/documents", files=_txt_file()).json()

    response = client.delete(f"/subjects/{subject_b}/documents/{created['id']}")

    assert response.status_code == 404
    assert client.get(f"/subjects/{subject_a}/documents/{created['id']}").status_code == 200


def test_delete_tolerates_an_r2_failure_and_still_removes_the_db_row(monkeypatch):
    # The DB delete has already committed by the time the R2 delete is attempted (see
    # service.delete_document's docstring) — a transient R2 failure must not turn an
    # already-successful deletion into a 500; it's logged and tolerated instead.
    monkeypatch.setattr(
        r2_client, "delete_object", lambda key: (_ for _ in ()).throw(RuntimeError("R2 down"))
    )
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()

    response = client.delete(f"/subjects/{subject_id}/documents/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/subjects/{subject_id}/documents/{created['id']}").status_code == 404


def test_delete_tolerates_a_document_with_no_r2_key(_mock_r2):
    # e.g. a legacy row from before r2_object_key existed — delete_document must not
    # crash trying to delete a None key.
    subject_id = _create_subject()
    created = client.post(f"/subjects/{subject_id}/documents", files=_txt_file()).json()
    with Session(_engine) as session:
        doc = documents_service.get_document_by_id(session, _TEST_USER, uuid.UUID(created["id"]))
        doc.r2_object_key = None
        session.add(doc)
        session.commit()

    response = client.delete(f"/subjects/{subject_id}/documents/{created['id']}")

    assert response.status_code == 204


_HAS_REAL_DB_AND_R2 = bool(get_settings().database_url) and bool(get_settings().r2_bucket_name)


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_REAL_DB_AND_R2, reason="requires DATABASE_URL (real Neon) and real R2 credentials"
)
def test_delete_document_removes_the_real_r2_object():
    """Live end-to-end: real Neon + real R2 — confirms the object is actually gone
    from the real bucket after delete_document, not just that the DB row is gone."""
    from app.core.db import get_engine
    from app.modules.subjects import service as subjects_service
    from app.modules.subjects.schemas import SubjectCreate

    r2_client._get_client.cache_clear()
    engine = get_engine()
    owner_id = "live_smoke_test_user_delete"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Delete Smoke Test")
        )
        document = documents_service.create_document(
            session,
            owner_id,
            subject.id,
            filename="delete-me.txt",
            content_type="text/plain",
            raw=b"This document will be deleted.",
        )
        r2_object_key = document.r2_object_key
        assert r2_object_key is not None
        assert r2_client.get_object(r2_object_key)  # confirm it's really there first

        try:
            deleted = documents_service.delete_document(session, owner_id, subject.id, document.id)
            assert deleted is True
            remaining = documents_service.get_document(session, owner_id, subject.id, document.id)
            assert remaining is None

            with pytest.raises(ClientError):
                r2_client.get_object(r2_object_key)  # confirmed gone from real R2
        finally:
            session.delete(subject)
            session.commit()
    r2_client._get_client.cache_clear()
