"""Tests for app.modules.documents.service.search_chunks.

pgvector's `<=>` cosine-distance operator only exists on Postgres, so search_chunks
skips similarity ordering entirely off it (see service.py). The SQLite tests below
only verify the WHERE-clause filtering — tenant scoping, subject scoping, and
excluding chunks with no embedding — with Cohere mocked (no network), and run in the
default `pytest` invocation.

Actual similarity *ordering* is verified separately against real Neon — marked `live`
(deselected by default; run explicitly with `pytest -m live`) and additionally guarded
with `skipif` on `DATABASE_URL` being configured at all, so `pytest -m live` still
skips cleanly rather than erroring in an environment with no real DB.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings
from app.modules.documents import service as documents_service
from app.modules.documents.embedding import EMBEDDING_DIM
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.subjects import service as subjects_service
from app.modules.subjects.schemas import SubjectCreate

_OWNER = "user_test_123"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@pytest.fixture(autouse=True)
def _fresh_schema():
    SQLModel.metadata.create_all(_engine)
    yield
    SQLModel.metadata.drop_all(_engine)


@pytest.fixture(autouse=True)
def _mock_cohere(monkeypatch):
    # search_chunks only calls embed_query on a real Postgres connection (see
    # service.py) — never reached by the SQLite tests below, but mocked anyway so
    # this file never makes a real network call regardless.
    monkeypatch.setattr(documents_service, "embed_query", lambda text: [0.0] * EMBEDDING_DIM)


def _make_subject(session: Session, owner_id: str, name: str = "Bio") -> uuid.UUID:
    subject = subjects_service.create_subject(session, owner_id, SubjectCreate(name=name))
    return subject.id


def _make_document(session: Session, owner_id: str, subject_id: uuid.UUID) -> uuid.UUID:
    document = Document(
        subject_id=subject_id,
        owner_id=owner_id,
        filename="f.txt",
        content_type="text/plain",
        status=DocumentStatus.READY,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document.id


_UNSET = object()  # distinguishes "caller didn't pass embedding" from "passed None"


def _make_chunk(
    session: Session,
    *,
    owner_id: str,
    subject_id: uuid.UUID,
    document_id: uuid.UUID,
    text: str = "chunk",
    embedding=_UNSET,
) -> None:
    if embedding is _UNSET:
        embedding = [0.1] * EMBEDDING_DIM
    session.add(
        DocumentChunk(
            document_id=document_id,
            subject_id=subject_id,
            owner_id=owner_id,
            chunk_index=0,
            text=text,
            embedding=embedding,
        )
    )
    session.commit()


def test_search_chunks_only_returns_matching_owner_and_subject():
    with Session(_engine) as session:
        subject_id = _make_subject(session, _OWNER)
        document_id = _make_document(session, _OWNER, subject_id)
        _make_chunk(
            session, owner_id=_OWNER, subject_id=subject_id, document_id=document_id, text="mine"
        )

        # a different subject, same owner
        other_subject_id = _make_subject(session, _OWNER, name="Chem")
        other_document_id = _make_document(session, _OWNER, other_subject_id)
        _make_chunk(
            session,
            owner_id=_OWNER,
            subject_id=other_subject_id,
            document_id=other_document_id,
            text="wrong subject",
        )

        # a different owner entirely, with their own subject of the same name
        their_subject_id = _make_subject(session, "someone_else")
        their_document_id = _make_document(session, "someone_else", their_subject_id)
        _make_chunk(
            session,
            owner_id="someone_else",
            subject_id=their_subject_id,
            document_id=their_document_id,
            text="wrong owner",
        )

        results = documents_service.search_chunks(session, _OWNER, subject_id, "anything")

        assert [chunk.text for chunk, _score in results] == ["mine"]


def test_search_chunks_excludes_chunks_without_embeddings():
    with Session(_engine) as session:
        subject_id = _make_subject(session, _OWNER)
        document_id = _make_document(session, _OWNER, subject_id)
        _make_chunk(
            session,
            owner_id=_OWNER,
            subject_id=subject_id,
            document_id=document_id,
            text="no embedding",
            embedding=None,
        )

        results = documents_service.search_chunks(session, _OWNER, subject_id, "anything")

        assert results == []


def test_search_chunks_respects_top_k():
    with Session(_engine) as session:
        subject_id = _make_subject(session, _OWNER)
        document_id = _make_document(session, _OWNER, subject_id)
        for i in range(5):
            _make_chunk(
                session,
                owner_id=_OWNER,
                subject_id=subject_id,
                document_id=document_id,
                text=f"chunk {i}",
            )

        results = documents_service.search_chunks(session, _OWNER, subject_id, "anything", top_k=2)

        assert len(results) == 2


def test_search_chunks_raises_for_missing_subject():
    with Session(_engine) as session:
        with pytest.raises(documents_service.SubjectNotFoundError):
            documents_service.search_chunks(session, _OWNER, uuid.uuid4(), "anything")


_HAS_REAL_DB = bool(get_settings().database_url)


@pytest.mark.live
@pytest.mark.skipif(not _HAS_REAL_DB, reason="requires DATABASE_URL (real Postgres/pgvector)")
def test_search_chunks_orders_by_similarity_against_real_neon():
    from app.core.db import get_engine

    engine = get_engine()
    owner_id = "live_smoke_test_user"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Search Smoke Test")
        )

        topics = {
            "photosynthesis.txt": (
                b"Photosynthesis converts sunlight into chemical energy in plant chloroplasts."
            ),
            "volcanoes.txt": (
                b"Volcanoes form when magma from within the Earth's mantle rises to the surface."
            ),
            "html.txt": b"HTML tags define the structure of a web page for browsers to render.",
        }
        created_docs = [
            documents_service.create_document(
                session,
                owner_id,
                subject.id,
                filename=filename,
                content_type="text/plain",
                raw=content,
            )
            for filename, content in topics.items()
        ]

        try:
            results = documents_service.search_chunks(
                session,
                owner_id,
                subject.id,
                "How do plants use sunlight to make energy?",
                top_k=3,
            )

            assert len(results) == 3
            top_chunk, _top_score = results[0]
            assert "Photosynthesis" in top_chunk.text

            scores = [score for _chunk, score in results]
            assert scores == sorted(scores, reverse=True)
        finally:
            # clean up in FK order: chunks -> documents -> subject
            for document in created_docs:
                for chunk in documents_service.list_chunks(session, owner_id, document.id):
                    session.delete(chunk)
            session.commit()
            for document in created_docs:
                session.delete(document)
            session.delete(subject)
            session.commit()
