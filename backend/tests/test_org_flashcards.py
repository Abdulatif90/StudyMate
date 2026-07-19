"""Cross-tenant isolation tests for flashcards over org-owned (read-shared) subjects —
Phase 5 increment 2b (the flashcard read-through). A bug here would let one student
mutate a teacher's schedule, leak another student's private cards, or generate/review
across org boundaries — so isolation and per-caller schedule independence are tested
exhaustively.

Same offline, isolated-SQLite pattern as test_org_subjects.py: `app.dependency_overrides`
swaps `get_session`, `get_current_user_id`, and `get_org_context` per test; identity
(who am I + which org is active) is switched mid-test via `_act_as`. Flashcard
generation (the Claude tool-use call) is stubbed so nothing hits the network; document
chunks are inserted directly (generation only reads chunk text).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.documents.embedding import EMBEDDING_DIM
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.flashcards import service as flashcards_service
from app.modules.flashcards.generation import GeneratedFlashcard
from app.modules.flashcards.models import Flashcard, FlashcardReviewState

# --- Identities -------------------------------------------------------------
# Org O: a teacher (admin) who owns the shared subject + its cards, plus two plain
# student members. Org O2: a separate org whose student must never see O's content.
TEACHER = "user_teacher_O"
STUDENT = "user_student_O"
STUDENT2 = "user_student2_O"
OTHER_ORG_STUDENT = "user_student_O2"
LONER = "user_no_org"  # signed in, no active organization

ORG_O = "org_O"
ORG_O2 = "org_O2"

_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"

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
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)  # default identity; tests switch via _act_as
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user_id, None)
    app.dependency_overrides.pop(get_org_context, None)
    SQLModel.metadata.drop_all(_engine)


@pytest.fixture(autouse=True)
def _mock_generation(monkeypatch):
    """Deterministic stand-in for Claude tool-use flashcard generation — no network."""
    monkeypatch.setattr(
        flashcards_service,
        "generate_flashcard_set",
        lambda excerpts, num_cards, language=None: _FAKE_CARDS,
    )


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _act_as(user_id: str, org_id: str | None, org_role: str | None) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_org_context] = lambda: OrgContext(org_id=org_id, org_role=org_role)


def _create_org_subject(name: str = "Shared Biology") -> str:
    """Teacher of org O creates a subject → published to the org (org_id set)."""
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["org_id"] == ORG_O
    return body["id"]


def _seed_chunks(owner_id: str, subject_id: str, texts: list[str]) -> None:
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


def _generate(subject_id: str) -> list[dict]:
    response = client.post(f"/subjects/{subject_id}/flashcards", json={})
    assert response.status_code == 201, response.text
    return response.json()


def _card_owner(card_id: str) -> str:
    with Session(_engine) as session:
        return session.get(Flashcard, uuid.UUID(card_id)).owner_id


# ---------------------------------------------------------------------------
# Generation over a shared subject → cards owned by the caller.
# ---------------------------------------------------------------------------


def test_member_generates_flashcards_over_teacher_org_subject_owned_by_member():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Photosynthesis converts sunlight into energy."])

    # The student member generates over the teacher's shared subject...
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    cards = _generate(subject_id)

    assert len(cards) == 2  # reader-variant sampling returned the TEACHER's chunks
    # ...and the resulting cards are owned by the STUDENT (per-student ownership).
    for card in cards:
        assert _card_owner(card["id"]) == STUDENT


def test_reader_sampling_returns_teacher_chunks_for_member():
    # Direct service-level check: the reader-scoped sampler sees the teacher's chunks
    # even though they aren't owned by the calling student (owner filter would be empty).
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Alpha.", "Beta.", "Gamma."])

    from app.modules.documents.service import sample_subject_chunk_texts_for_reader

    with Session(_engine) as session:
        texts = sample_subject_chunk_texts_for_reader(
            session, STUDENT, OrgContext(org_id=ORG_O, org_role=_ROLE_MEMBER), uuid.UUID(subject_id)
        )
    assert set(texts) == {"Alpha.", "Beta.", "Gamma."}


def test_loner_with_no_active_org_cannot_generate_over_org_subject():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(LONER, None, None)
    assert client.post(f"/subjects/{subject_id}/flashcards", json={}).status_code == 404


def test_member_of_different_org_cannot_generate_over_org_subject():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.post(f"/subjects/{subject_id}/flashcards", json={}).status_code == 404


# ---------------------------------------------------------------------------
# Listing over a shared subject: own + teacher's cards, per-caller schedule,
# never another student's private cards.
# ---------------------------------------------------------------------------


def test_member_list_includes_own_and_teacher_cards_not_other_students():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    # Teacher generates the shared set.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    teacher_cards = {c["id"] for c in _generate(subject_id)}

    # A DIFFERENT student generates their own private cards over the same subject.
    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    student2_cards = {c["id"] for c in _generate(subject_id)}

    # The student generates their own cards, then lists.
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    student_cards = {c["id"] for c in _generate(subject_id)}
    listed = {c["id"] for c in client.get(f"/subjects/{subject_id}/flashcards").json()}

    assert student_cards <= listed  # own cards
    assert teacher_cards <= listed  # the shared (owner's) set
    assert listed.isdisjoint(student2_cards)  # NOT another student's private cards


def test_teacher_list_shows_only_own_cards_over_own_shared_subject():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    teacher_cards = {c["id"] for c in _generate(subject_id)}

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    student_cards = {c["id"] for c in _generate(subject_id)}

    # The subject owner sees ONLY their own inline-scheduled cards, not a student's.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    listed = {c["id"] for c in client.get(f"/subjects/{subject_id}/flashcards").json()}
    assert listed == teacher_cards
    assert listed.isdisjoint(student_cards)


def test_member_sees_default_schedule_for_unreviewed_teacher_card():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    teacher_card = _generate(subject_id)[0]

    # Advance the teacher's OWN schedule, so the inline columns are clearly non-default.
    client.post(f"/flashcards/{teacher_card['id']}/review", json={"grade": 5})

    # The student, who's never reviewed it, sees a brand-new default schedule — NOT the
    # teacher's advanced one.
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    listed = client.get(f"/subjects/{subject_id}/flashcards").json()
    seen = next(c for c in listed if c["id"] == teacher_card["id"])
    assert seen["repetitions"] == 0
    assert seen["interval_days"] == 0
    assert seen["last_reviewed_at"] is None
    assert seen["ease_factor"] == pytest.approx(2.5)


def test_member_cannot_list_over_org_subject_of_another_org():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.get(f"/subjects/{subject_id}/flashcards").status_code == 404


# ---------------------------------------------------------------------------
# Review: non-owner keeps a private schedule; the owner's inline schedule and
# every other reviewer's schedule stay independent.
# ---------------------------------------------------------------------------


def _review_states(card_id: str) -> list[FlashcardReviewState]:
    with Session(_engine) as session:
        return list(
            session.exec(
                select(FlashcardReviewState).where(
                    FlashcardReviewState.flashcard_id == uuid.UUID(card_id)
                )
            )
        )


def test_non_owner_review_upserts_review_state_without_touching_owner_inline():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = client.post(f"/flashcards/{card['id']}/review", json={"grade": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == card["id"]  # the CARD's id, not the review-state row's
    assert body["repetitions"] == 1

    # Exactly one review-state row (for the student), and the teacher's inline schedule
    # is untouched (still a brand-new card).
    states = _review_states(card["id"])
    assert len(states) == 1
    assert states[0].owner_id == STUDENT
    assert states[0].repetitions == 1
    with Session(_engine) as session:
        teacher_card = session.get(Flashcard, uuid.UUID(card["id"]))
    assert teacher_card.repetitions == 0
    assert teacher_card.last_reviewed_at is None


def test_two_students_keep_independent_schedules_over_the_same_card():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    client.post(f"/flashcards/{card['id']}/review", json={"grade": 5})
    client.post(f"/flashcards/{card['id']}/review", json={"grade": 5})
    student_body = client.post(f"/flashcards/{card['id']}/review", json={"grade": 5}).json()

    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    student2_body = client.post(f"/flashcards/{card['id']}/review", json={"grade": 3}).json()

    assert student_body["repetitions"] == 3
    assert student2_body["repetitions"] == 1  # independent, unaffected by STUDENT
    states = {s.owner_id: s.repetitions for s in _review_states(card["id"])}
    assert states == {STUDENT: 3, STUDENT2: 1}


def test_owner_review_of_own_card_uses_inline_columns_no_review_state():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    body = client.post(f"/flashcards/{card['id']}/review", json={"grade": 4}).json()
    assert body["repetitions"] == 1
    # No review-state row is ever created for the owner — they use the inline columns.
    assert _review_states(card["id"]) == []
    with Session(_engine) as session:
        assert session.get(Flashcard, uuid.UUID(card["id"])).repetitions == 1


def test_member_cannot_review_another_students_private_card():
    # Cross-student isolation: a student's own cards over a shared subject are PRIVATE
    # (owner_id-scoped) — only the subject owner's cards are shared. Student B, a member
    # of the same org who knows student A's card id, must NOT be able to review it.
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])

    # Student A generates their own private card over the shared subject.
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    card = _generate(subject_id)[0]
    assert _card_owner(card["id"]) == STUDENT

    # Student B (same org) tries to review A's private card by id → denied, no state row.
    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    assert client.post(f"/flashcards/{card['id']}/review", json={"grade": 5}).status_code == 404
    assert _review_states(card["id"]) == []


def test_member_of_different_org_cannot_review_org_card():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert client.post(f"/flashcards/{card['id']}/review", json={"grade": 5}).status_code == 404
    assert _review_states(card["id"]) == []  # nothing written


# ---------------------------------------------------------------------------
# /due respects the CALLER's effective schedule, not the owner's.
# ---------------------------------------------------------------------------


def test_due_uses_caller_review_state_not_owner_schedule():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    # Student first sees the teacher's card as due (brand-new default = due now).
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    due_ids = {c["id"] for c in client.get(f"/subjects/{subject_id}/flashcards/due").json()}
    assert card["id"] in due_ids

    # After a passing review, the student's OWN schedule pushes it out ~1 day → not due.
    client.post(f"/flashcards/{card['id']}/review", json={"grade": 5})
    due_ids = {c["id"] for c in client.get(f"/subjects/{subject_id}/flashcards/due").json()}
    assert card["id"] not in due_ids

    # ...but the TEACHER's own inline schedule is untouched, so it's still due for them.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    due_ids = {c["id"] for c in client.get(f"/subjects/{subject_id}/flashcards/due").json()}
    assert card["id"] in due_ids


# ---------------------------------------------------------------------------
# Delete: owner-only. A student can't delete a teacher's shared card; the owner's
# delete cleans up every reviewer's review-state rows.
# ---------------------------------------------------------------------------


def test_member_cannot_delete_teacher_shared_card():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert client.delete(f"/flashcards/{card['id']}").status_code == 404
    with Session(_engine) as session:
        assert session.get(Flashcard, uuid.UUID(card["id"])) is not None  # still there


def test_owner_delete_removes_card_and_all_reviewer_states():
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    # Two students each build a private schedule over the teacher's card.
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    client.post(f"/flashcards/{card['id']}/review", json={"grade": 5})
    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    client.post(f"/flashcards/{card['id']}/review", json={"grade": 4})
    assert len(_review_states(card["id"])) == 2

    # The owner deletes the card → the card AND both review-state rows are gone.
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    assert client.delete(f"/flashcards/{card['id']}").status_code == 204
    with Session(_engine) as session:
        assert session.get(Flashcard, uuid.UUID(card["id"])) is None
    assert _review_states(card["id"]) == []


def test_due_now_override_is_respected_for_reader_schedule():
    # Service-level: pin the clock so a reviewed shared card is or isn't due deterministically.
    subject_id = _create_org_subject()
    _seed_chunks(TEACHER, subject_id, ["Material."])
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    card = _generate(subject_id)[0]

    org = OrgContext(org_id=ORG_O, org_role=_ROLE_MEMBER)
    with Session(_engine) as session:
        # Student reviews at a fixed time; interval becomes 1 day.
        review_time = datetime(2026, 7, 19, tzinfo=UTC)
        flashcards_service.review_flashcard(
            session, STUDENT, org, uuid.UUID(card["id"]), grade=5, now=review_time
        )
        # Same day: not due yet for the student.
        due_same_day = flashcards_service.list_due_flashcards_for_reader(
            session, STUDENT, org, uuid.UUID(subject_id), now=review_time
        )
        assert uuid.UUID(card["id"]) not in {s.id for s in due_same_day}
        # Two days later: due again.
        due_later = flashcards_service.list_due_flashcards_for_reader(
            session, STUDENT, org, uuid.UUID(subject_id), now=review_time + timedelta(days=2)
        )
        assert uuid.UUID(card["id"]) in {s.id for s in due_later}
