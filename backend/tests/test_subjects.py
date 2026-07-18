"""Tests for the subjects module — router + service, against an in-memory SQLite DB.

Overrides `get_session`/`get_current_user_id` per-test (set up and torn down by a
fixture, not at import time) so nothing leaks into other test modules that share
the same `app` instance.

`delete_subject`'s cascade (documents/quizzes/flashcards/conversations) is tested at
the service layer directly, not through the four generation endpoints (which would
need Claude/Cohere mocked too) — child rows are constructed directly via each
module's own models, mirroring test_progress.py's hand-built-fixture pattern. R2 is
mocked the same way test_documents.py does it (`_mock_r2`, autouse, skipped for
`@pytest.mark.live` tests), so this stays network-free by default.
"""

from __future__ import annotations

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
from app.modules.ask import service as ask_service
from app.modules.ask.models import Conversation, ConversationTurn
from app.modules.documents import service as documents_service
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.flashcards import service as flashcards_service
from app.modules.flashcards.models import Flashcard
from app.modules.quiz import service as quiz_service
from app.modules.quiz.models import Quiz, QuizQuestion
from app.modules.subjects import service as subjects_service
from app.modules.subjects.models import Subject
from app.modules.subjects.schemas import SubjectCreate

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


@pytest.fixture(autouse=True)
def _mock_r2(request, monkeypatch):
    """In-memory stand-in for R2 — same pattern as test_documents.py's `_mock_r2`:
    put/get/delete against a dict, no network. Returned so tests can assert
    `delete_subject`'s cascade actually removed each document's R2 object. Skipped for
    `@pytest.mark.live` tests, which deliberately want the real `r2_client` functions.
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


client = TestClient(app)


def _seed_full_subject_content(
    session: Session, owner_id: str, subject_id, r2_store: dict, *, suffix: str
) -> dict:
    """Insert one document (+ chunk, + R2 object), one quiz (+ question), one
    flashcard, and one conversation (+ turn) for `owner_id`/`subject_id` — directly via
    each module's own models, not through the real generation/ingest pipeline (which
    would need Claude/Cohere mocked too; this only cares whether `delete_subject`'s
    cascade finds and removes each child type, not how they were created). `suffix`
    keeps values distinguishable across the two owners this test seeds identically.
    """
    document = Document(
        subject_id=subject_id,
        owner_id=owner_id,
        filename=f"doc-{suffix}.txt",
        content_type="text/plain",
        status=DocumentStatus.READY,
        r2_object_key=f"{owner_id}/doc-{suffix}",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    r2_store[document.r2_object_key] = b"content"
    session.add(
        DocumentChunk(
            document_id=document.id,
            subject_id=subject_id,
            owner_id=owner_id,
            chunk_index=0,
            text=f"chunk-{suffix}",
        )
    )

    quiz = Quiz(subject_id=subject_id, owner_id=owner_id, title=f"quiz-{suffix}")
    session.add(quiz)
    session.commit()
    session.refresh(quiz)
    session.add(
        QuizQuestion(
            quiz_id=quiz.id,
            owner_id=owner_id,
            question=f"q-{suffix}",
            options=["a", "b"],
            correct_index=0,
            order=0,
        )
    )

    flashcard = Flashcard(
        subject_id=subject_id, owner_id=owner_id, front=f"front-{suffix}", back=f"back-{suffix}"
    )
    session.add(flashcard)

    conversation = Conversation(subject_id=subject_id, owner_id=owner_id, title=f"conv-{suffix}")
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    session.add(
        ConversationTurn(
            conversation_id=conversation.id,
            owner_id=owner_id,
            question=f"turn-q-{suffix}",
            answer=f"turn-a-{suffix}",
            sources=[],
        )
    )
    session.commit()

    return {
        "document_id": document.id,
        "r2_key": document.r2_object_key,
        "quiz_id": quiz.id,
        "flashcard_id": flashcard.id,
        "conversation_id": conversation.id,
    }


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


def test_delete_subject_cascades_to_all_child_data_and_leaves_other_owners_untouched(_mock_r2):
    other_owner = "someone_else"
    with Session(_engine) as session:
        subject_a = Subject(owner_id=_TEST_USER, name="Mine")
        subject_b = Subject(owner_id=other_owner, name="Also has content, different owner")
        session.add(subject_a)
        session.add(subject_b)
        session.commit()
        session.refresh(subject_a)
        session.refresh(subject_b)

        mine = _seed_full_subject_content(
            session, _TEST_USER, subject_a.id, _mock_r2, suffix="mine"
        )
        theirs = _seed_full_subject_content(
            session, other_owner, subject_b.id, _mock_r2, suffix="theirs"
        )

        deleted = subjects_service.delete_subject(session, _TEST_USER, subject_a.id)
        assert deleted is True

        # Every child row for the deleted subject is actually gone, not just
        # unreachable — list_questions/list_turns don't filter by subject, so a
        # non-empty result here would mean the rows still exist in the DB.
        assert subjects_service.get_subject(session, _TEST_USER, subject_a.id) is None
        assert (
            documents_service.get_document(session, _TEST_USER, subject_a.id, mine["document_id"])
            is None
        )
        assert documents_service.list_chunks(session, _TEST_USER, mine["document_id"]) == []
        assert quiz_service.get_quiz(session, _TEST_USER, subject_a.id, mine["quiz_id"]) is None
        assert quiz_service.list_questions(session, _TEST_USER, mine["quiz_id"]) == []
        assert flashcards_service.get_flashcard(session, _TEST_USER, mine["flashcard_id"]) is None
        assert ask_service.get_conversation(session, _TEST_USER, mine["conversation_id"]) is None
        assert ask_service.list_turns(session, _TEST_USER, mine["conversation_id"]) == []
        assert mine["r2_key"] not in _mock_r2

        # The cross-tenant assertion: a second owner's IDENTICALLY-SHAPED data is
        # completely untouched by owner one's subject deletion.
        assert subjects_service.get_subject(session, other_owner, subject_b.id) is not None
        assert (
            documents_service.get_document(
                session, other_owner, subject_b.id, theirs["document_id"]
            )
            is not None
        )
        assert len(documents_service.list_chunks(session, other_owner, theirs["document_id"])) == 1
        assert (
            quiz_service.get_quiz(session, other_owner, subject_b.id, theirs["quiz_id"]) is not None
        )
        assert len(quiz_service.list_questions(session, other_owner, theirs["quiz_id"])) == 1
        assert (
            flashcards_service.get_flashcard(session, other_owner, theirs["flashcard_id"])
            is not None
        )
        assert (
            ask_service.get_conversation(session, other_owner, theirs["conversation_id"])
            is not None
        )
        assert len(ask_service.list_turns(session, other_owner, theirs["conversation_id"])) == 1
        assert theirs["r2_key"] in _mock_r2


def test_delete_subject_with_no_content_still_cascades_cleanly():
    """The empty-subject case, extended to prove the cascade's enumeration loops are
    genuine no-ops (not skipped/short-circuited) when a subject has no children at
    all — same assertion as test_delete_subject_removes_it, at the service layer."""
    with Session(_engine) as session:
        subject = Subject(owner_id=_TEST_USER, name="Empty")
        session.add(subject)
        session.commit()
        session.refresh(subject)

        deleted = subjects_service.delete_subject(session, _TEST_USER, subject.id)
        assert deleted is True
        assert subjects_service.get_subject(session, _TEST_USER, subject.id) is None


_HAS_REAL_DB_AND_R2 = bool(get_settings().database_url) and bool(get_settings().r2_bucket_name)


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_REAL_DB_AND_R2, reason="requires DATABASE_URL (real Neon) and real R2 credentials"
)
def test_delete_subject_removes_all_content_and_the_real_r2_object():
    """Live end-to-end: real Neon + real R2 — a subject with a real ingested document
    (chunks + embeddings via the real create_document/process_document pipeline, the
    same one other live tests use) is deleted via delete_subject. Confirms both the DB
    rows AND the real R2 object are gone, not just that the Subject row disappeared."""
    from app.core.db import get_engine

    r2_client._get_client.cache_clear()
    engine = get_engine()
    owner_id = "live_smoke_test_user_subject_cascade"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Cascade Delete Smoke Test")
        )
        document = documents_service.create_document(
            session,
            owner_id,
            subject.id,
            filename="cascade-delete-me.txt",
            content_type="text/plain",
            raw=b"This subject and everything in it will be deleted.",
        )
        documents_service.process_document(session, owner_id, document.id)
        r2_object_key = document.r2_object_key
        assert r2_object_key is not None
        assert r2_client.get_object(r2_object_key)  # confirm it's really there first
        assert documents_service.list_chunks(session, owner_id, document.id)  # really chunked

        try:
            deleted = subjects_service.delete_subject(session, owner_id, subject.id)
            assert deleted is True

            assert subjects_service.get_subject(session, owner_id, subject.id) is None
            assert (
                documents_service.get_document(session, owner_id, subject.id, document.id) is None
            )
            assert documents_service.list_chunks(session, owner_id, document.id) == []
            with pytest.raises(ClientError):
                r2_client.get_object(r2_object_key)  # confirmed gone from real R2
        finally:
            # Defensive cleanup in case an assertion above failed mid-way —
            # delete_subject itself should already have removed everything (that's
            # exactly what's under test here).
            remaining = subjects_service.get_subject(session, owner_id, subject.id)
            if remaining is not None:
                session.delete(remaining)
                session.commit()
    r2_client._get_client.cache_clear()
