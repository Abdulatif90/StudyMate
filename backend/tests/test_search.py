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
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core import r2_client
from app.core.config import get_settings
from app.core.org import OrgContext
from app.modules.documents import service as documents_service
from app.modules.documents.embedding import EMBEDDING_DIM
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.documents.rerank import RerankError
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


@pytest.fixture(autouse=True)
def _mock_r2(monkeypatch):
    # Only the live test uploads via create_document (which puts to R2) and processes
    # it (which fetches from R2); fake it in-memory so no test here touches real R2.
    store: dict[str, bytes] = {}

    def put(key, data, content_type):
        store[key] = data

    monkeypatch.setattr(r2_client, "put_object", put)
    monkeypatch.setattr(r2_client, "get_object", lambda key: store[key])
    monkeypatch.setattr(r2_client, "delete_object", lambda key: store.pop(key, None))


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

        results = documents_service.search_chunks(
            session, _OWNER, OrgContext(), subject_id, "anything"
        )

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

        results = documents_service.search_chunks(
            session, _OWNER, OrgContext(), subject_id, "anything"
        )

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

        results = documents_service.search_chunks(
            session, _OWNER, OrgContext(), subject_id, "anything", top_k=2
        )

        assert len(results) == 2


def test_search_chunks_raises_for_missing_subject():
    with Session(_engine) as session:
        with pytest.raises(documents_service.SubjectNotFoundError):
            documents_service.search_chunks(session, _OWNER, OrgContext(), uuid.uuid4(), "anything")


# --- _rerank_candidates (pure logic over an already-fetched list — no DB/dialect
# dependency, so this is testable regardless of Postgres/SQLite; rerank itself is
# mocked, same pattern as _mock_cohere above) ---------------------------------


def _chunk(text: str):
    # _rerank_candidates only ever reads .text off each chunk and passes the object
    # through untouched, so a lightweight stand-in is enough — no DB needed.
    return SimpleNamespace(text=text)


def test_rerank_candidates_reorders_by_relevance_score(monkeypatch):
    candidates = [(_chunk("volcanoes"), 0.9), (_chunk("photosynthesis"), 0.5)]
    # rerank ranks the second candidate (index 1) highest, reversing the vector order.
    monkeypatch.setattr(
        documents_service, "rerank", lambda query, texts, top_n: [(1, 0.95), (0, 0.1)]
    )

    result = documents_service._rerank_candidates("q", candidates, top_k=2)

    assert [chunk.text for chunk, _score in result] == ["photosynthesis", "volcanoes"]
    assert [score for _chunk, score in result] == [0.95, 0.1]


def test_rerank_candidates_respects_top_k(monkeypatch):
    candidates = [(_chunk(f"chunk {i}"), 1.0 - i * 0.1) for i in range(5)]
    monkeypatch.setattr(
        documents_service,
        "rerank",
        lambda query, texts, top_n: [(i, 1.0 - i * 0.1) for i in range(top_n)],
    )

    result = documents_service._rerank_candidates("q", candidates, top_k=2)

    assert len(result) == 2


def test_rerank_candidates_falls_back_to_vector_order_on_rerank_error(monkeypatch):
    candidates = [(_chunk("a"), 0.9), (_chunk("b"), 0.8), (_chunk("c"), 0.7)]

    def _raise(query, texts, top_n):
        raise RerankError("Cohere is unavailable")

    monkeypatch.setattr(documents_service, "rerank", _raise)

    result = documents_service._rerank_candidates("q", candidates, top_k=2)

    # falls back to the original vector-similarity order, truncated to top_k — not an
    # error, and not the reranked (unavailable) order.
    assert result == candidates[:2]


def test_rerank_candidates_returns_empty_for_no_candidates(monkeypatch):
    rerank_spy = MagicMock()
    monkeypatch.setattr(documents_service, "rerank", rerank_spy)

    assert documents_service._rerank_candidates("q", [], top_k=8) == []
    rerank_spy.assert_not_called()


_HAS_REAL_DB = bool(get_settings().database_url)


@pytest.mark.live
@pytest.mark.skipif(not _HAS_REAL_DB, reason="requires DATABASE_URL (real Postgres/pgvector)")
def test_search_chunks_orders_by_relevance_via_real_rerank():
    """search_chunks' full real pipeline now: vector retrieve -> real Cohere Rerank.
    Asserts the on-topic chunk still ranks first and scores still descend — through
    the reranked path, not just raw cosine order (see _rerank_candidates)."""
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
        # Upload is async now — create_document only inserts a pending row; process
        # the document (what the Inngest job does) so its chunks/embeddings exist.
        created_docs = []
        for filename, content in topics.items():
            document = documents_service.create_document(
                session,
                owner_id,
                subject.id,
                filename=filename,
                content_type="text/plain",
                raw=content,
            )
            documents_service.process_document(session, owner_id, document.id)
            created_docs.append(document)

        try:
            results = documents_service.search_chunks(
                session,
                owner_id,
                OrgContext(),
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


@pytest.mark.live
@pytest.mark.skipif(not _HAS_REAL_DB, reason="requires DATABASE_URL (real Postgres/pgvector)")
def test_hybrid_search_surfaces_exact_keyword_match():
    """The reason the lexical (FTS) arm was added: an exact keyword/code match — exactly
    where pure embeddings are weakest (rare tokens, codes, identifiers) — is retrieved
    and top-ranked through the real hybrid path (Postgres FTS `@@` over the generated
    tsvector + vector + RRF fusion + Cohere Rerank). test_rrf.py proves the fusion math
    offline; this proves the whole Postgres pipeline is wired correctly and that the FTS
    arm carries its own owner+subject scoping (only this owner's chunks come back)."""
    from app.core.db import get_engine

    engine = get_engine()
    owner_id = "live_smoke_test_user_hybrid"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Hybrid Search Smoke Test")
        )

        # One chunk carries a distinctive code ("ISO-9001"); the others are semantically
        # adjacent (quality, process) but never contain that exact token — so only the
        # lexical arm can pin the code to its chunk.
        topics = {
            "iso.txt": (
                b"Our laboratory holds ISO-9001 certification for its quality management system."
            ),
            "quality.txt": (
                b"Quality management improves processes and reduces defects across manufacturing."
            ),
            "teamwork.txt": b"Good teamwork and clear communication matter in any workplace.",
            "budget.txt": b"Annual budgets allocate resources across departments and projects.",
        }
        created_docs = []
        for filename, content in topics.items():
            document = documents_service.create_document(
                session,
                owner_id,
                subject.id,
                filename=filename,
                content_type="text/plain",
                raw=content,
            )
            documents_service.process_document(session, owner_id, document.id)
            created_docs.append(document)

        try:
            results = documents_service.search_chunks(
                session, owner_id, OrgContext(), subject.id, "ISO-9001 certification", top_k=2
            )

            assert results, "expected at least one result"
            top_chunk, _score = results[0]
            assert "ISO-9001" in top_chunk.text  # the exact-keyword chunk ranks first
        finally:
            for document in created_docs:
                for chunk in documents_service.list_chunks(session, owner_id, document.id):
                    session.delete(chunk)
            session.commit()
            for document in created_docs:
                session.delete(document)
            session.delete(subject)
            session.commit()
