"""Tests for the Ask endpoint (app.modules.ask) — router + service, against an
in-memory SQLite DB. Mirrors tests/test_documents.py's isolation pattern.

search_chunks skips its Cohere call entirely off Postgres (see documents/service.py),
so on SQLite only document upload (which calls embed_texts) needs Cohere mocked —
the ask flow itself only needs Claude (ask_claude) mocked. Real end-to-end behavior
(real retrieval ranking + real Claude generation) is covered by the `live` test at
the bottom, against real Neon — skipped by default, run with `pytest -m live`.
"""

from __future__ import annotations

import io
import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core import r2_client
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.ask import service as ask_service
from app.modules.documents import service as documents_service
from app.modules.documents.embedding import EMBEDDING_DIM


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parses a raw SSE response body into `(event, data)` pairs, matching the
    `event: <name>\\ndata: <json>\\n\\n` shape `service.stream_answer` writes.
    """
    events = []
    for block in body.strip("\n").split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        event = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


_TEST_USER = "user_test_123"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _get_test_session():
    with Session(_engine) as session:
        yield session


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    return [[0.1] * EMBEDDING_DIM for _ in texts]


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
def _mock_summarization(monkeypatch):
    # _upload_txt calls process_document directly (see below), which also generates a
    # summary now — mocked so these ask/RAG tests never touch the network for it.
    monkeypatch.setattr(
        documents_service, "summarize_document", lambda text, language=None: "A short summary."
    )


@pytest.fixture(autouse=True)
def _mock_inngest(monkeypatch):
    # Upload emits an Inngest event now; mock it so these tests never hit the network.
    # _upload_txt processes the document explicitly instead (see below).
    monkeypatch.setattr(documents_service, "enqueue_document_processing", lambda document: None)


@pytest.fixture(autouse=True)
def _mock_r2(monkeypatch):
    # Upload stores the file in R2 and the job fetches it back; fake it with an
    # in-memory dict so these tests (ask/RAG, not R2) never touch the network. Real R2
    # is round-tripped in tests/test_r2_client.py.
    store: dict[str, bytes] = {}

    def put(key, data, content_type):
        store[key] = data

    monkeypatch.setattr(r2_client, "put_object", put)
    monkeypatch.setattr(r2_client, "get_object", lambda key: store[key])
    monkeypatch.setattr(r2_client, "delete_object", lambda key: store.pop(key, None))


client = TestClient(app)
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _create_subject(name: str = "Biology") -> str:
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _upload_txt(
    subject_id: str, content: bytes = b"Photosynthesis converts sunlight into energy."
) -> dict:
    """Upload a document AND run its processing synchronously — upload alone now only
    creates a `pending` row (processing is async), but the ask tests need the chunks
    to exist to have anything to retrieve."""
    files = {"file": ("notes.txt", io.BytesIO(content), "text/plain")}
    response = client.post(f"/subjects/{subject_id}/documents", files=files)
    assert response.status_code == 201
    document = response.json()
    with Session(_engine) as session:
        documents_service.process_document(session, _TEST_USER, uuid.UUID(document["id"]))
    return document


def test_ask_returns_answer_and_sources(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)

    mock_ask_claude = MagicMock(return_value="Plants use sunlight via photosynthesis.")
    monkeypatch.setattr(ask_service, "ask_claude", mock_ask_claude)

    response = client.post(
        f"/subjects/{subject_id}/ask", json={"question": "How do plants use sunlight?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Plants use sunlight via photosynthesis."
    assert body["conversation_id"]
    assert len(body["sources"]) == 1
    assert body["sources"][0]["filename"] == "notes.txt"
    assert body["sources"][0]["chunk_index"] == 0
    assert "Photosynthesis" in body["sources"][0]["text"]

    # confirm the retrieved chunk's context was actually passed to Claude
    question_arg, chunks_arg = mock_ask_claude.call_args[0]
    assert question_arg == "How do plants use sunlight?"
    assert chunks_arg[0]["filename"] == "notes.txt"
    assert "Photosynthesis" in chunks_arg[0]["text"]


def test_ask_returns_404_for_missing_subject():
    response = client.post(f"/subjects/{_MISSING_ID}/ask", json={"question": "anything?"})
    assert response.status_code == 404


def test_ask_returns_404_for_another_owners_subject():
    subject_id = _create_subject()
    _upload_txt(subject_id)

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})
    assert response.status_code == 404


def test_ask_with_no_documents_returns_graceful_no_material_message(monkeypatch):
    subject_id = _create_subject()  # no documents uploaded — nothing to retrieve

    mock_ask_claude = MagicMock()
    monkeypatch.setattr(ask_service, "ask_claude", mock_ask_claude)

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert "couldn't find" in body["answer"].lower()
    mock_ask_claude.assert_not_called()  # nothing to ground on — never even calls Claude


def test_ask_gracefully_handles_llm_failure(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)

    monkeypatch.setattr(
        ask_service, "ask_claude", MagicMock(side_effect=ask_service.LLMError("boom"))
    )

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert "try again" in body["answer"].lower()


def test_ask_without_conversation_id_creates_a_new_conversation(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    monkeypatch.setattr(ask_service, "ask_claude", MagicMock(return_value="An answer."))

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "Q1"})
    conversation_id = response.json()["conversation_id"]

    conversation = client.get(f"/conversations/{conversation_id}")
    assert conversation.status_code == 200
    body = conversation.json()
    assert body["subject_id"] == subject_id
    assert len(body["turns"]) == 1
    assert body["turns"][0]["question"] == "Q1"
    assert body["turns"][0]["answer"] == "An answer."


def test_ask_follow_up_reuses_conversation_and_passes_prior_context(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    mock_ask_claude = MagicMock(side_effect=["First answer.", "Second answer."])
    monkeypatch.setattr(ask_service, "ask_claude", mock_ask_claude)

    first = client.post(f"/subjects/{subject_id}/ask", json={"question": "What is photosynthesis?"})
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        f"/subjects/{subject_id}/ask",
        json={"question": "Can you give an example?", "conversation_id": conversation_id},
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    # the second call must have received the first Q&A as prior context
    second_call = mock_ask_claude.call_args_list[1]
    assert second_call.args[0] == "Can you give an example?"
    assert second_call.kwargs["prior_turns"] == [
        {"question": "What is photosynthesis?", "answer": "First answer."}
    ]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert [t["question"] for t in conversation["turns"]] == [
        "What is photosynthesis?",
        "Can you give an example?",
    ]
    assert [t["answer"] for t in conversation["turns"]] == ["First answer.", "Second answer."]


def test_ask_returns_404_for_conversation_from_a_different_subject(monkeypatch):
    subject_a = _create_subject(name="Bio")
    subject_b = _create_subject(name="Chem")
    _upload_txt(subject_a)
    _upload_txt(subject_b)
    monkeypatch.setattr(ask_service, "ask_claude", MagicMock(return_value="An answer."))

    first = client.post(f"/subjects/{subject_a}/ask", json={"question": "Q1"})
    conversation_id = first.json()["conversation_id"]

    response = client.post(
        f"/subjects/{subject_b}/ask",
        json={"question": "Q2", "conversation_id": conversation_id},
    )
    assert response.status_code == 404


def test_turn_is_saved_even_when_no_relevant_material(monkeypatch):
    subject_id = _create_subject()  # no documents uploaded
    monkeypatch.setattr(ask_service, "ask_claude", MagicMock())

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})
    conversation_id = response.json()["conversation_id"]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert len(conversation["turns"]) == 1
    assert conversation["turns"][0]["question"] == "anything?"
    assert "couldn't find" in conversation["turns"][0]["answer"].lower()
    assert conversation["turns"][0]["sources"] == []


def test_turn_is_saved_even_when_llm_fails(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    monkeypatch.setattr(
        ask_service, "ask_claude", MagicMock(side_effect=ask_service.LLMError("boom"))
    )

    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "anything?"})
    conversation_id = response.json()["conversation_id"]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert len(conversation["turns"]) == 1
    assert "try again" in conversation["turns"][0]["answer"].lower()


def test_list_conversations_is_owner_scoped(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    monkeypatch.setattr(ask_service, "ask_claude", MagicMock(return_value="An answer."))
    client.post(f"/subjects/{subject_id}/ask", json={"question": "Q1"})

    own_list = client.get("/conversations")
    assert own_list.status_code == 200
    assert len(own_list.json()) == 1

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    other_list = client.get("/conversations")
    assert other_list.json() == []


def test_get_conversation_returns_404_for_another_owner(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    monkeypatch.setattr(ask_service, "ask_claude", MagicMock(return_value="An answer."))
    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "Q1"})
    conversation_id = response.json()["conversation_id"]

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    get_response = client.get(f"/conversations/{conversation_id}")
    assert get_response.status_code == 404


def test_get_conversation_returns_404_when_missing():
    response = client.get(f"/conversations/{_MISSING_ID}")
    assert response.status_code == 404


def test_delete_conversation_removes_it_and_its_turns(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    monkeypatch.setattr(ask_service, "ask_claude", MagicMock(return_value="An answer."))
    response = client.post(f"/subjects/{subject_id}/ask", json={"question": "Q1"})
    conversation_id = response.json()["conversation_id"]

    delete_response = client.delete(f"/conversations/{conversation_id}")
    assert delete_response.status_code == 204

    assert client.get(f"/conversations/{conversation_id}").status_code == 404


def test_delete_conversation_returns_404_when_missing():
    response = client.delete(f"/conversations/{_MISSING_ID}")
    assert response.status_code == 404


# --- Streaming (POST /subjects/{subject_id}/ask/stream) ---------------------


def test_ask_stream_returns_token_events_then_a_done_event(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    monkeypatch.setattr(
        ask_service,
        "ask_claude_stream",
        MagicMock(return_value=iter(["Plants ", "use ", "sunlight."])),
    )

    response = client.post(
        f"/subjects/{subject_id}/ask/stream", json={"question": "How do plants use sunlight?"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)

    token_events = [data for event, data in events[:-1] if event == "token"]
    assert [e["text"] for e in token_events] == ["Plants ", "use ", "sunlight."]

    final_event, final_data = events[-1]
    assert final_event == "done"
    assert final_data["conversation_id"]
    assert final_data["turn_id"]
    assert len(final_data["sources"]) == 1
    assert final_data["sources"][0]["filename"] == "notes.txt"

    # persisted exactly once, with the full concatenated answer
    conversation = client.get(f"/conversations/{final_data['conversation_id']}").json()
    assert len(conversation["turns"]) == 1
    assert conversation["turns"][0]["answer"] == "Plants use sunlight."
    assert conversation["turns"][0]["question"] == "How do plants use sunlight?"


def test_ask_stream_returns_404_for_missing_subject():
    response = client.post(f"/subjects/{_MISSING_ID}/ask/stream", json={"question": "anything?"})
    assert response.status_code == 404


def test_ask_stream_returns_404_for_another_owners_subject():
    subject_id = _create_subject()
    _upload_txt(subject_id)

    app.dependency_overrides[get_current_user_id] = lambda: "someone_else"
    response = client.post(f"/subjects/{subject_id}/ask/stream", json={"question": "anything?"})
    assert response.status_code == 404


def test_ask_stream_with_no_documents_returns_graceful_no_material_message(monkeypatch):
    subject_id = _create_subject()  # no documents uploaded — nothing to retrieve
    mock_stream = MagicMock()
    monkeypatch.setattr(ask_service, "ask_claude_stream", mock_stream)

    response = client.post(f"/subjects/{subject_id}/ask/stream", json={"question": "anything?"})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert len(events) == 2  # one token event, one done event
    assert events[0] == ("token", {"text": ask_service._NO_MATERIAL_ANSWER})
    assert events[1][1]["sources"] == []
    mock_stream.assert_not_called()  # nothing to ground on — never even calls Claude


def test_ask_stream_gracefully_handles_llm_failure_before_any_delta(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)

    def _raise(*_args, **_kwargs):
        raise ask_service.LLMError("boom")
        yield  # pragma: no cover - makes this a generator function, never reached

    monkeypatch.setattr(ask_service, "ask_claude_stream", _raise)

    response = client.post(f"/subjects/{subject_id}/ask/stream", json={"question": "anything?"})

    events = _parse_sse(response.text)
    assert events[0] == ("token", {"text": ask_service._GENERATION_FAILED_ANSWER})
    assert events[-1][1]["sources"] == []


def test_ask_stream_persists_partial_answer_when_llm_fails_partway(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)

    def _partial_then_fail(*_args, **_kwargs):
        yield "Photo"
        yield "synthesis"
        raise ask_service.LLMError("connection dropped")

    monkeypatch.setattr(ask_service, "ask_claude_stream", _partial_then_fail)

    response = client.post(f"/subjects/{subject_id}/ask/stream", json={"question": "anything?"})

    events = _parse_sse(response.text)
    token_texts = [data["text"] for event, data in events if event == "token"]
    assert token_texts == ["Photo", "synthesis"]

    final_data = events[-1][1]
    # real (if partial) grounded output — keep the sources, don't discard them
    assert len(final_data["sources"]) == 1

    conversation = client.get(f"/conversations/{final_data['conversation_id']}").json()
    assert conversation["turns"][0]["answer"] == "Photosynthesis"


def test_ask_stream_turn_is_saved_even_when_no_relevant_material(monkeypatch):
    subject_id = _create_subject()  # no documents uploaded
    monkeypatch.setattr(ask_service, "ask_claude_stream", MagicMock())

    response = client.post(f"/subjects/{subject_id}/ask/stream", json={"question": "anything?"})
    conversation_id = _parse_sse(response.text)[-1][1]["conversation_id"]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert len(conversation["turns"]) == 1
    assert "couldn't find" in conversation["turns"][0]["answer"].lower()
    assert conversation["turns"][0]["sources"] == []


def test_ask_stream_follow_up_reuses_conversation_and_passes_prior_context(monkeypatch):
    subject_id = _create_subject()
    _upload_txt(subject_id)
    mock_stream = MagicMock(side_effect=[iter(["First answer."]), iter(["Second answer."])])
    monkeypatch.setattr(ask_service, "ask_claude_stream", mock_stream)

    first = client.post(
        f"/subjects/{subject_id}/ask/stream", json={"question": "What is photosynthesis?"}
    )
    conversation_id = _parse_sse(first.text)[-1][1]["conversation_id"]

    second = client.post(
        f"/subjects/{subject_id}/ask/stream",
        json={"question": "Can you give an example?", "conversation_id": conversation_id},
    )

    assert _parse_sse(second.text)[-1][1]["conversation_id"] == conversation_id

    second_call = mock_stream.call_args_list[1]
    assert second_call.args[0] == "Can you give an example?"
    assert second_call.kwargs["prior_turns"] == [
        {"question": "What is photosynthesis?", "answer": "First answer."}
    ]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert [t["question"] for t in conversation["turns"]] == [
        "What is photosynthesis?",
        "Can you give an example?",
    ]
    assert [t["answer"] for t in conversation["turns"]] == ["First answer.", "Second answer."]


def test_ask_stream_returns_404_for_conversation_from_a_different_subject(monkeypatch):
    subject_a = _create_subject(name="Bio")
    subject_b = _create_subject(name="Chem")
    _upload_txt(subject_a)
    _upload_txt(subject_b)
    monkeypatch.setattr(
        ask_service, "ask_claude_stream", MagicMock(return_value=iter(["An answer."]))
    )

    first = client.post(f"/subjects/{subject_a}/ask/stream", json={"question": "Q1"})
    conversation_id = _parse_sse(first.text)[-1][1]["conversation_id"]

    response = client.post(
        f"/subjects/{subject_b}/ask/stream",
        json={"question": "Q2", "conversation_id": conversation_id},
    )
    assert response.status_code == 404


_HAS_REAL_DB = bool(get_settings().database_url)


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_REAL_DB, reason="requires DATABASE_URL (real Neon) and a real Claude key"
)
def test_ask_end_to_end_against_real_neon_and_claude():
    from app.core.db import get_engine
    from app.modules.ask.service import ask_question, delete_conversation
    from app.modules.subjects import service as subjects_service
    from app.modules.subjects.schemas import SubjectCreate

    engine = get_engine()
    owner_id = "live_smoke_test_user"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Ask Smoke Test")
        )
        document = documents_service.create_document(
            session,
            owner_id,
            subject.id,
            filename="photosynthesis.txt",
            content_type="text/plain",
            raw=(
                b"Photosynthesis converts sunlight into chemical energy in plant "
                b"chloroplasts. Chlorophyll absorbs sunlight."
            ),
        )
        # Upload is async now — run the processing (what the Inngest job does) so the
        # document's chunks/embeddings exist for retrieval.
        documents_service.process_document(session, owner_id, document.id)

        try:
            response = ask_question(session, owner_id, subject.id, "How do plants use sunlight?")

            assert response.sources, "expected at least one source chunk"
            assert "photosynthesis.txt" in [source.filename for source in response.sources]
            assert len(response.answer) > 0
            assert "n't find" not in response.answer.lower()  # actually grounded, not a refusal

            # a real follow-up, in the same conversation, with real Claude context
            follow_up = ask_question(
                session,
                owner_id,
                subject.id,
                "Can you say that in one short sentence?",
                conversation_id=response.conversation_id,
            )
            assert follow_up.conversation_id == response.conversation_id

            turns = ask_service.list_turns(session, owner_id, response.conversation_id)
            assert len(turns) == 2
        finally:
            delete_conversation(session, owner_id, response.conversation_id)
            for chunk in documents_service.list_chunks(session, owner_id, document.id):
                session.delete(chunk)
            session.commit()
            session.delete(document)
            session.delete(subject)
            session.commit()


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_REAL_DB, reason="requires DATABASE_URL (real Neon) and a real Claude key"
)
def test_ask_stream_end_to_end_against_real_neon_cohere_and_claude():
    """Same shape as the non-stream live test above, but drives the real SSE
    generator directly (bypassing HTTP/TestClient, same reasoning as every other
    live test in this file — no real Clerk JWT available outside a browser)."""
    from app.core.db import get_engine
    from app.modules.ask.service import delete_conversation, prepare_ask_stream, stream_answer
    from app.modules.subjects import service as subjects_service
    from app.modules.subjects.schemas import SubjectCreate

    engine = get_engine()
    owner_id = "live_smoke_test_user_stream"
    with Session(engine) as session:
        subject = subjects_service.create_subject(
            session, owner_id, SubjectCreate(name="Ask Stream Smoke Test")
        )
        document = documents_service.create_document(
            session,
            owner_id,
            subject.id,
            filename="photosynthesis.txt",
            content_type="text/plain",
            raw=(
                b"Photosynthesis converts sunlight into chemical energy in plant "
                b"chloroplasts. Chlorophyll absorbs sunlight."
            ),
        )
        # Upload is async now — run the processing (what the Inngest job does) so the
        # document's chunks/embeddings exist for retrieval.
        documents_service.process_document(session, owner_id, document.id)

        conversation_id = None
        try:
            context = prepare_ask_stream(
                session, owner_id, subject.id, "How do plants use sunlight?"
            )
            assert context.has_material

            events = _parse_sse("".join(stream_answer(session, owner_id, context)))
            done_event, done_data = events[-1]
            assert done_event == "done"

            conversation_id = context.conversation_id
            full_answer = "".join(data["text"] for event, data in events[:-1] if event == "token")
            assert len(full_answer) > 0
            assert "n't find" not in full_answer.lower()  # actually grounded, not a refusal
            assert done_data["sources"], "expected at least one source chunk in the done event"

            turns = ask_service.list_turns(session, owner_id, conversation_id)
            assert len(turns) == 1
            assert turns[0].answer == full_answer  # persisted text matches streamed text exactly
        finally:
            if conversation_id is not None:
                delete_conversation(session, owner_id, conversation_id)
            for chunk in documents_service.list_chunks(session, owner_id, document.id):
                session.delete(chunk)
            session.commit()
            session.delete(document)
            session.delete(subject)
            session.commit()
