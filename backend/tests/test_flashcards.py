"""Tests for the flashcards module — router + service, against an in-memory SQLite DB.
Mirrors tests/test_quiz.py's isolation pattern (per-test dependency overrides).

Flashcard generation (the Claude tool-use call) is mocked at the service boundary
(`generate_flashcard_set`) so the default suite never touches the network — the real
tool-use call is unit-tested in test_flashcard_generation.py, SM-2 scheduling itself in
test_sm2.py, and the whole pipeline exercised end-to-end by the `live` test at the
bottom (real Neon + Cohere + Claude). Chunks are inserted directly (no R2/Inngest
needed) since generation only reads chunk text.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
from app.modules.flashcards import service as flashcards_service
from app.modules.flashcards.generation import FlashcardGenerationError, GeneratedFlashcard
from app.modules.flashcards.models import Flashcard

_TEST_USER = "user_test_123"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)

_FAKE_CARDS = [
    GeneratedFlashcard(front="What does photosynthesis convert?", back="Sunlight into energy"),
    GeneratedFlashcard(front="What pigment absorbs light?", back="Chlorophyll"),
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
    """Deterministic stand-in for Claude tool-use flashcard generation — autouse so no
    test here makes a network call. Skipped for `@pytest.mark.live` tests, which want
    the real generation path."""
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(
        flashcards_service, "generate_flashcard_set", lambda excerpts, num_cards: _FAKE_CARDS
    )


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _create_subject(name: str = "Biology") -> str:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _seed_chunks(owner_id: str, subject_id: str, texts: list[str]) -> None:
    """Insert a document + its chunks straight into the DB — generation only reads
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


def _generate(subject_id: str, num_cards: int | None = None) -> list[dict]:
    body = {} if num_cards is None else {"num_cards": num_cards}
    response = client.post(f"/subjects/{subject_id}/flashcards", json=body)
    assert response.status_code == 201
    return response.json()


# --- Generate (POST /subjects/{subject_id}/flashcards) ----------------------


def test_generate_flashcards_creates_cards_with_default_sr_state():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Photosynthesis converts sunlight into energy."])

    cards = _generate(subject_id)

    assert len(cards) == 2
    first = cards[0]
    assert first["front"] == _FAKE_CARDS[0].front
    assert first["back"] == _FAKE_CARDS[0].back
    assert first["repetitions"] == 0
    assert first["ease_factor"] == pytest.approx(2.5)
    assert first["interval_days"] == 0
    assert first["last_reviewed_at"] is None
    assert "owner_id" not in first
    # a new card is due immediately, not at some future offset. SQLite (the test
    # engine) round-trips datetimes without tzinfo, so compare naive-to-naive.
    due_at = datetime.fromisoformat(first["due_at"])
    assert due_at <= datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=5)


def test_generate_flashcards_persists_and_is_listed():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Some material."])
    _generate(subject_id)

    listed = client.get(f"/subjects/{subject_id}/flashcards")
    assert listed.status_code == 200
    assert len(listed.json()) == 2


def test_generate_flashcards_returns_404_for_missing_subject():
    response = client.post(f"/subjects/{_MISSING_ID}/flashcards", json={})
    assert response.status_code == 404


def test_generate_flashcards_returns_404_for_another_owners_subject():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.post(f"/subjects/{subject_id}/flashcards", json={})
    assert response.status_code == 404


def test_generate_flashcards_returns_422_when_subject_has_no_material():
    subject_id = _create_subject()  # no chunks seeded

    response = client.post(f"/subjects/{subject_id}/flashcards", json={})
    assert response.status_code == 422


def test_generate_flashcards_returns_502_on_generation_failure(monkeypatch):
    def _raise(excerpts, num_cards):
        raise FlashcardGenerationError("Claude is unavailable")

    monkeypatch.setattr(flashcards_service, "generate_flashcard_set", _raise)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])

    response = client.post(f"/subjects/{subject_id}/flashcards", json={})
    assert response.status_code == 502


def test_generate_flashcards_persists_nothing_on_generation_failure(monkeypatch):
    def _raise(excerpts, num_cards):
        raise FlashcardGenerationError("Claude is unavailable")

    monkeypatch.setattr(flashcards_service, "generate_flashcard_set", _raise)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    client.post(f"/subjects/{subject_id}/flashcards", json={})

    assert client.get(f"/subjects/{subject_id}/flashcards").json() == []


def test_generate_flashcards_passes_num_cards_through(monkeypatch):
    captured = {}

    def _capture(excerpts, num_cards):
        captured["n"] = num_cards
        return _FAKE_CARDS

    monkeypatch.setattr(flashcards_service, "generate_flashcard_set", _capture)

    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    _generate(subject_id, num_cards=25)

    assert captured["n"] == 25


def test_generate_flashcards_rejects_out_of_bounds_num_cards():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])

    too_few = client.post(f"/subjects/{subject_id}/flashcards", json={"num_cards": 0})
    too_many = client.post(f"/subjects/{subject_id}/flashcards", json={"num_cards": 51})
    assert too_few.status_code == 422
    assert too_many.status_code == 422


# --- List / due ---------------------------------------------------------------


def test_list_flashcards_returns_404_for_missing_subject():
    assert client.get(f"/subjects/{_MISSING_ID}/flashcards").status_code == 404


def test_list_flashcards_is_owner_scoped():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    _generate(subject_id)

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    # someone_else doesn't own the subject → 404 (not an empty list)
    assert client.get(f"/subjects/{subject_id}/flashcards").status_code == 404


def test_due_flashcards_includes_newly_generated_cards():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    _generate(subject_id)  # new cards are due immediately

    due = client.get(f"/subjects/{subject_id}/flashcards/due")
    assert due.status_code == 200
    assert len(due.json()) == 2


def test_due_flashcards_excludes_not_yet_due_cards():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    cards = _generate(subject_id)

    # push one card's due date into the future directly (no HTTP way to do this yet —
    # only a real review advances it, which is tested separately below)
    with Session(_engine) as session:
        flashcard = session.get(Flashcard, uuid.UUID(cards[0]["id"]))
        flashcard.due_at = datetime.now(UTC) + timedelta(days=30)
        session.add(flashcard)
        session.commit()

    due = client.get(f"/subjects/{subject_id}/flashcards/due")
    assert due.status_code == 200
    due_ids = {card["id"] for card in due.json()}
    assert cards[0]["id"] not in due_ids
    assert cards[1]["id"] in due_ids


# --- Review (POST /flashcards/{id}/review) -----------------------------------


def test_review_with_passing_grade_advances_the_schedule():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    card = _generate(subject_id)[0]

    response = client.post(f"/flashcards/{card['id']}/review", json={"grade": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["repetitions"] == 1
    assert body["interval_days"] == 1
    assert body["last_reviewed_at"] is not None
    # due_at moved forward from the original (due-immediately) value
    original_due = datetime.fromisoformat(card["due_at"].replace("Z", "+00:00"))
    new_due = datetime.fromisoformat(body["due_at"].replace("Z", "+00:00"))
    assert new_due > original_due


def test_review_with_lapse_grade_resets_repetitions():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    card = _generate(subject_id)[0]

    # build up some progress first
    client.post(f"/flashcards/{card['id']}/review", json={"grade": 5})
    after_success = client.post(f"/flashcards/{card['id']}/review", json={"grade": 5}).json()
    assert after_success["repetitions"] == 2

    lapsed = client.post(f"/flashcards/{card['id']}/review", json={"grade": 1}).json()
    assert lapsed["repetitions"] == 0
    assert lapsed["interval_days"] == 1


@pytest.mark.parametrize("grade", [-1, 6])
def test_review_rejects_out_of_range_grade(grade):
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    card = _generate(subject_id)[0]

    response = client.post(f"/flashcards/{card['id']}/review", json={"grade": grade})
    assert response.status_code == 422


def test_review_returns_404_when_missing():
    response = client.post(f"/flashcards/{_MISSING_ID}/review", json={"grade": 4})
    assert response.status_code == 404


def test_review_returns_404_for_another_owners_card():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    card = _generate(subject_id)[0]

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.post(f"/flashcards/{card['id']}/review", json={"grade": 4})
    assert response.status_code == 404


# --- Delete (DELETE /flashcards/{id}) ----------------------------------------


def test_delete_flashcard_removes_it():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    card = _generate(subject_id)[0]

    response = client.delete(f"/flashcards/{card['id']}")

    assert response.status_code == 204
    assert response.content == b""
    listed = client.get(f"/subjects/{subject_id}/flashcards").json()
    assert card["id"] not in {c["id"] for c in listed}


def test_delete_flashcard_returns_404_when_missing():
    assert client.delete(f"/flashcards/{_MISSING_ID}").status_code == 404


def test_delete_flashcard_returns_404_for_another_owner_and_leaves_it_intact():
    subject_id = _create_subject()
    _seed_chunks(_TEST_USER, subject_id, ["Material."])
    card = _generate(subject_id)[0]

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    assert client.delete(f"/flashcards/{card['id']}").status_code == 404

    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    listed = client.get(f"/subjects/{subject_id}/flashcards").json()
    assert card["id"] in {c["id"] for c in listed}


# --- Live (real Neon + Cohere + Claude tool-use) -----------------------------


@pytest.fixture(autouse=True)
def _mock_r2(request, monkeypatch):
    """In-memory R2 for the live test's create_document/process_document byte
    round-trip (real Cohere/Claude still run). Offline tests seed chunks directly and
    never touch R2, so this is harmless there."""
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
def test_generate_and_review_flashcard_end_to_end_against_real_neon_cohere_and_claude():
    from app.core.db import get_engine
    from app.modules.documents import service as documents_service
    from app.modules.subjects import service as subjects_service
    from app.modules.subjects.schemas import SubjectCreate

    r2_client._get_client.cache_clear()
    engine = get_engine()
    owner_id = "live_smoke_test_user_flashcards"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Flashcards Smoke Test")
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

        flashcards: list[Flashcard] = []
        try:
            flashcards = flashcards_service.generate_flashcards(
                session, owner_id, subject.id, num_cards=3
            )
            assert len(flashcards) >= 1
            for card in flashcards:
                assert card.front.strip()
                assert card.back.strip()
                assert card.repetitions == 0
                assert card.ease_factor == pytest.approx(2.5)

            # review_flashcard looks the card up in this same session, so it returns
            # the SAME identity-mapped object as flashcards[0] — snapshot the
            # pre-review due_at as a plain value first, or comparing "before" and
            # "after" would just compare the mutated object to itself.
            original_due_at = flashcards[0].due_at

            reviewed = flashcards_service.review_flashcard(
                session, owner_id, flashcards[0].id, grade=5
            )
            assert reviewed is not None
            assert reviewed.repetitions == 1
            assert reviewed.interval_days == 1
            assert reviewed.last_reviewed_at is not None
            assert reviewed.due_at > original_due_at
        finally:
            for flashcard in flashcards:
                session.delete(flashcard)
            session.commit()
            for chunk in documents_service.list_chunks(session, owner_id, document.id):
                session.delete(chunk)
            session.commit()
            r2_object_key = document.r2_object_key
            session.delete(document)
            session.commit()
            session.delete(subject)
            session.commit()
            # the live test suite for quiz/search leaves the R2 object orphaned after
            # this point — deliberately not repeating that gap here.
            if r2_object_key is not None:
                r2_client.delete_object(r2_object_key)
    r2_client._get_client.cache_clear()
