"""Tests for the subjects module — router + service, against an in-memory SQLite DB.

Overrides `get_session`/`get_current_user_id` per-test (set up and torn down by a
fixture, not at import time) so nothing leaks into other test modules that share
the same `app` instance.
"""

from __future__ import annotations

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


def test_create_and_list_subjects():
    response = client.post("/subjects", json={"name": "Biology"})
    assert response.status_code == 201
    assert response.json()["name"] == "Biology"

    response = client.get("/subjects")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_subject_returns_404_when_missing():
    response = client.get("/subjects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_subjects_are_scoped_to_owner():
    client.post("/subjects", json={"name": "Mine"})

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.get("/subjects")
    assert response.json() == []


def test_delete_subject_removes_it():
    created = client.post("/subjects", json={"name": "ToDelete"}).json()

    response = client.delete(f"/subjects/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/subjects/{created['id']}").status_code == 404


def test_delete_subject_returns_404_when_missing():
    response = client.delete("/subjects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
