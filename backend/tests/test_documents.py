"""Tests for the documents module — router + service, against an in-memory SQLite DB.

Mirrors tests/test_subjects.py's isolation pattern (see there for why overrides are
scoped per-test rather than at import time). Text-only, no R2/Cohere/Inngest: uploads
are parsed synchronously in-request, so status resolves straight to ready/failed.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.main import app

_TEST_USER = "user_test_123"
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
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    yield
    del app.dependency_overrides[get_session]
    del app.dependency_overrides[get_current_user_id]
    SQLModel.metadata.drop_all(_engine)


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _create_subject(name: str = "Biology") -> str:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _txt_file(content: bytes = b"hello world"):
    return {"file": ("notes.txt", io.BytesIO(content), "text/plain")}


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
