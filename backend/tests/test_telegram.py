"""Tests for the Telegram bot module — link + webhook, fully offline.

The Telegram Bot API (`send_message`) and the Research service (`research`) are ALWAYS
mocked here — no test calls either for real. Same isolated in-memory SQLite +
`app.dependency_overrides` pattern as test_subjects.py (set up/torn down per test so
nothing leaks into other modules sharing the same `app`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.ask.schemas import AskResponse, SourceChunk
from app.modules.research.schemas import ResearchResponse, ResearchSource
from app.modules.subjects.models import Subject
from app.modules.telegram import service, telegram_api
from app.modules.telegram.models import TelegramLink, TelegramLinkCode

_TEST_USER = "user_owner_A"
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


@pytest.fixture
def session():
    with Session(_engine) as s:
        yield s


@pytest.fixture
def mock_send(monkeypatch):
    """Replace the Bot API send with a spy — no network, records every reply."""
    spy = Mock()
    monkeypatch.setattr(service, "send_message", spy)
    return spy


@pytest.fixture
def mock_research(monkeypatch):
    """Replace the Research service with a spy returning a canned grounded answer."""
    spy = Mock(
        return_value=ResearchResponse(
            answer="Photosynthesis converts light into chemical energy.",
            sources=[ResearchSource(title="Bio", url="https://example.com/bio")],
        )
    )
    monkeypatch.setattr(service, "research", spy)
    return spy


@pytest.fixture
def mock_ask(monkeypatch):
    """Replace the Ask/RAG service with a spy returning a canned grounded answer over the
    user's own materials. Keeps these tests offline (no Cohere/Claude) and focused on the
    Telegram command/routing/scoping logic — the RAG pipeline itself is covered in
    test_ask.py / test_search.py."""

    def _fake(session, owner_id, subject_id, question, org_ctx=None):
        return AskResponse(
            answer="Mitochondria are the powerhouse of the cell.",
            sources=[
                SourceChunk(
                    document_id=uuid.uuid4(),
                    filename="biology.pdf",
                    chunk_index=0,
                    text="...",
                    similarity_score=0.9,
                )
            ],
            conversation_id=uuid.uuid4(),
        )

    spy = Mock(side_effect=_fake)
    monkeypatch.setattr(service, "ask_question", spy)
    return spy


def _make_subject(session, owner_id: str, name: str) -> Subject:
    subject = Subject(owner_id=owner_id, name=name)
    session.add(subject)
    session.commit()
    session.refresh(subject)
    return subject


def _text_update(chat_id: int, text: str) -> dict:
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


# --- link codes -------------------------------------------------------------------------


def test_create_link_code_returns_code_and_deep_link(session):
    result = service.create_link_code(session, _TEST_USER)

    assert result.code
    assert result.deep_link == f"https://t.me/helperstudymatebot?start={result.code}"
    stored = session.get(TelegramLinkCode, result.code)
    assert stored is not None
    assert stored.owner_id == _TEST_USER
    assert stored.used is False


def test_valid_start_code_links_chat_and_consumes_code(session, mock_send, mock_research):
    code = service.create_link_code(session, _TEST_USER).code

    service.handle_update(session, _text_update(555, f"/start {code}"))

    links = session.exec(select(TelegramLink)).all()
    assert len(links) == 1
    assert links[0].telegram_chat_id == 555
    assert links[0].owner_id == _TEST_USER
    assert session.get(TelegramLinkCode, code).used is True
    mock_send.assert_called_once()
    mock_research.assert_not_called()  # linking never triggers research


def test_unknown_code_replies_friendly_and_does_not_link(session, mock_send):
    service.handle_update(session, _text_update(555, "/start NOPE123"))

    assert session.exec(select(TelegramLink)).all() == []
    (chat_id, text), _ = mock_send.call_args
    assert chat_id == 555
    assert "invalid or has expired" in text


def test_used_code_cannot_link_again(session, mock_send):
    code = service.create_link_code(session, _TEST_USER).code
    service.handle_update(session, _text_update(555, f"/start {code}"))
    mock_send.reset_mock()

    # A different chat tries to reuse the now-consumed code.
    service.handle_update(session, _text_update(999, f"/start {code}"))

    assert session.get(TelegramLink, 999) is None
    (_, text), _ = mock_send.call_args
    assert "invalid or has expired" in text


def test_expired_code_rejected(session, mock_send):
    code = service.create_link_code(session, _TEST_USER).code
    stale = session.get(TelegramLinkCode, code)
    stale.created_at = datetime.now(UTC) - timedelta(hours=2)
    session.add(stale)
    session.commit()

    service.handle_update(session, _text_update(555, f"/start {code}"))

    assert session.exec(select(TelegramLink)).all() == []
    (_, text), _ = mock_send.call_args
    assert "invalid or has expired" in text


def test_start_without_code_replies_instructions(session, mock_send):
    service.handle_update(session, _text_update(555, "/start"))

    assert session.exec(select(TelegramLink)).all() == []
    (_, text), _ = mock_send.call_args
    assert "connect your account" in text.lower()


# --- answering --------------------------------------------------------------------------


def test_linked_chat_text_triggers_research_and_answer(session, mock_send, mock_research):
    session.add(TelegramLink(telegram_chat_id=555, owner_id=_TEST_USER))
    session.commit()

    service.handle_update(session, _text_update(555, "What is photosynthesis?"))

    mock_research.assert_called_once_with("What is photosynthesis?")
    (chat_id, text), _ = mock_send.call_args
    assert chat_id == 555
    assert "Photosynthesis converts light" in text
    assert "https://example.com/bio" in text  # sources footer included


def test_unlinked_chat_text_gets_instructions_and_no_research(session, mock_send, mock_research):
    service.handle_update(session, _text_update(555, "What is photosynthesis?"))

    mock_research.assert_not_called()
    (chat_id, text), _ = mock_send.call_args
    assert chat_id == 555
    assert "isn't connected" in text


def test_answer_truncated_to_telegram_limit(session, mock_send, monkeypatch):
    session.add(TelegramLink(telegram_chat_id=555, owner_id=_TEST_USER))
    session.commit()
    monkeypatch.setattr(
        service,
        "research",
        Mock(return_value=ResearchResponse(answer="x" * 5000, sources=[])),
    )

    service.handle_update(session, _text_update(555, "long please"))

    (_, text), _ = mock_send.call_args
    assert len(text) <= telegram_api.MAX_MESSAGE_LENGTH


def test_research_unexpected_failure_replies_friendly(session, mock_send, monkeypatch):
    session.add(TelegramLink(telegram_chat_id=555, owner_id=_TEST_USER))
    session.commit()
    monkeypatch.setattr(service, "research", Mock(side_effect=RuntimeError("boom")))

    service.handle_update(session, _text_update(555, "hello"))

    (_, text), _ = mock_send.call_args
    assert "couldn't answer" in text.lower()


# --- answering over the user's OWN materials (subjects) ---------------------------------


def _link(session, chat_id: int, owner_id: str, active_subject_id=None) -> None:
    session.add(
        TelegramLink(
            telegram_chat_id=chat_id, owner_id=owner_id, active_subject_id=active_subject_id
        )
    )
    session.commit()


def test_subjects_command_lists_owner_subjects(session, mock_send):
    _link(session, 555, _TEST_USER)
    _make_subject(session, _TEST_USER, "Biology")
    _make_subject(session, _TEST_USER, "History")

    service.handle_update(session, _text_update(555, "/subjects"))

    (chat_id, text), _ = mock_send.call_args
    assert chat_id == 555
    assert "Biology" in text
    assert "History" in text
    assert "/subject" in text


def test_subjects_command_no_subjects_prompts_to_create(session, mock_send):
    _link(session, 555, _TEST_USER)

    service.handle_update(session, _text_update(555, "/subjects"))

    (_, text), _ = mock_send.call_args
    assert "don't have any subjects" in text.lower()


def test_subject_command_by_number_sets_active(session, mock_send):
    _link(session, 555, _TEST_USER)
    _make_subject(session, _TEST_USER, "Biology")
    _make_subject(session, _TEST_USER, "History")
    ordered = service.list_owned_subjects(session, _TEST_USER)

    service.handle_update(session, _text_update(555, "/subject 2"))

    link = session.get(TelegramLink, 555)
    assert link.active_subject_id == ordered[1].id
    (_, text), _ = mock_send.call_args
    assert ordered[1].name in text


def test_subject_command_by_name_sets_active(session, mock_send):
    _link(session, 555, _TEST_USER)
    bio = _make_subject(session, _TEST_USER, "Biology")
    _make_subject(session, _TEST_USER, "History")

    service.handle_update(session, _text_update(555, "/subject biology"))  # case-insensitive

    assert session.get(TelegramLink, 555).active_subject_id == bio.id


def test_subject_command_unknown_replies_not_found(session, mock_send):
    _link(session, 555, _TEST_USER)
    _make_subject(session, _TEST_USER, "Biology")

    service.handle_update(session, _text_update(555, "/subject 99"))

    assert session.get(TelegramLink, 555).active_subject_id is None
    (_, text), _ = mock_send.call_args
    assert "couldn't find that subject" in text.lower()


def test_subject_command_no_arg_shows_listing(session, mock_send):
    _link(session, 555, _TEST_USER)
    _make_subject(session, _TEST_USER, "Biology")

    service.handle_update(session, _text_update(555, "/subject"))

    (_, text), _ = mock_send.call_args
    assert "Biology" in text


def test_question_over_active_subject_uses_ask_service(session, mock_send, mock_ask, mock_research):
    bio = _make_subject(session, _TEST_USER, "Biology")
    _link(session, 555, _TEST_USER, active_subject_id=bio.id)

    service.handle_update(session, _text_update(555, "What are mitochondria?"))

    # RAG, not web research.
    mock_research.assert_not_called()
    mock_ask.assert_called_once()
    # ask_question(session, owner_id, subject_id, question, org_ctx=...) — all positional.
    _args, _kwargs = mock_ask.call_args
    _session, owner_id, subject_id, question = _args
    assert owner_id == _TEST_USER
    assert subject_id == bio.id
    assert question == "What are mitochondria?"
    (_, text), _ = mock_send.call_args
    assert "powerhouse of the cell" in text
    assert "biology.pdf" in text  # source filename footer


def test_question_without_active_subject_prompts_pick(session, mock_send, mock_ask, mock_research):
    _link(session, 555, _TEST_USER)
    _make_subject(session, _TEST_USER, "Biology")

    service.handle_update(session, _text_update(555, "What are mitochondria?"))

    # Has subjects but none selected → prompt, don't answer.
    mock_ask.assert_not_called()
    mock_research.assert_not_called()
    (_, text), _ = mock_send.call_args
    assert "Biology" in text
    assert "/subject" in text


def test_question_no_subjects_falls_back_to_research(session, mock_send, mock_ask, mock_research):
    _link(session, 555, _TEST_USER)  # no subjects at all

    service.handle_update(session, _text_update(555, "What is photosynthesis?"))

    mock_ask.assert_not_called()
    mock_research.assert_called_once_with("What is photosynthesis?")


def test_deleted_active_subject_clears_and_prompts(session, mock_send, monkeypatch):
    bio = _make_subject(session, _TEST_USER, "Biology")
    _link(session, 555, _TEST_USER, active_subject_id=bio.id)
    # Simulate the subject having been deleted after selection: ask_question fails closed.
    monkeypatch.setattr(
        service, "ask_question", Mock(side_effect=service.SubjectNotFoundError(bio.id))
    )

    service.handle_update(session, _text_update(555, "What are mitochondria?"))

    assert session.get(TelegramLink, 555).active_subject_id is None
    (_, text), _ = mock_send.call_args
    assert "no longer available" in text.lower()


def test_question_ask_unexpected_failure_replies_friendly(session, mock_send, monkeypatch):
    bio = _make_subject(session, _TEST_USER, "Biology")
    _link(session, 555, _TEST_USER, active_subject_id=bio.id)
    monkeypatch.setattr(service, "ask_question", Mock(side_effect=RuntimeError("boom")))

    service.handle_update(session, _text_update(555, "What are mitochondria?"))

    (_, text), _ = mock_send.call_args
    assert "couldn't answer" in text.lower()


def test_research_command_calls_research(session, mock_send, mock_research, mock_ask):
    bio = _make_subject(session, _TEST_USER, "Biology")
    _link(session, 555, _TEST_USER, active_subject_id=bio.id)  # active subject present

    service.handle_update(session, _text_update(555, "/research quantum tunneling"))

    # /research forces web research even with an active subject; RAG not used.
    mock_ask.assert_not_called()
    mock_research.assert_called_once_with("quantum tunneling")


def test_research_command_no_query_prompts(session, mock_send, mock_research):
    _link(session, 555, _TEST_USER)

    service.handle_update(session, _text_update(555, "/research"))

    mock_research.assert_not_called()
    (_, text), _ = mock_send.call_args
    assert "what would you like me to research" in text.lower()


def test_help_and_unknown_command_reply_help(session, mock_send):
    _link(session, 555, _TEST_USER)

    service.handle_update(session, _text_update(555, "/help"))
    (_, help_text), _ = mock_send.call_args
    assert "/subjects" in help_text and "/research" in help_text

    mock_send.reset_mock()
    service.handle_update(session, _text_update(555, "/wat"))
    (_, unknown_text), _ = mock_send.call_args
    assert "/subjects" in unknown_text


def test_command_from_unlinked_chat_gets_instructions(session, mock_send, mock_ask):
    service.handle_update(session, _text_update(555, "/subjects"))

    mock_ask.assert_not_called()
    (_, text), _ = mock_send.call_args
    assert "isn't connected" in text


def test_subject_selection_is_owner_scoped(session, mock_send):
    # Owner A's chat must only ever see and select A's subjects, never B's.
    _make_subject(session, "owner_B", "Secret B Subject")
    a_bio = _make_subject(session, _TEST_USER, "A Biology")
    _link(session, 555, _TEST_USER)

    service.handle_update(session, _text_update(555, "/subjects"))
    (_, listing), _ = mock_send.call_args
    assert "Secret B Subject" not in listing
    assert "A Biology" in listing

    # Only one subject visible to A, so number 1 resolves to A's own subject.
    service.handle_update(session, _text_update(555, "/subject 1"))
    assert session.get(TelegramLink, 555).active_subject_id == a_bio.id


# --- defensive parsing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "update",
    [
        {},
        {"update_id": 1},
        {"message": {}},
        {"message": {"chat": {}, "text": "hi"}},
        {"message": {"chat": {"id": 5}}},  # no text
        {"message": {"chat": {"id": 5}, "text": "   "}},  # whitespace only
        {"message": {"chat": {"id": 5}, "text": 123}},  # non-string text
    ],
)
def test_malformed_update_is_noop(session, mock_send, mock_research, update):
    service.handle_update(session, update)  # must not raise

    mock_send.assert_not_called()
    mock_research.assert_not_called()


# --- cross-tenant isolation -------------------------------------------------------------


def test_code_for_owner_a_links_to_a_not_b(session, mock_send):
    # Code minted for owner A; even if owner B's chat redeems it, it links to A (the code
    # carries A's owner_id — the redeemer never supplies an owner).
    code = service.create_link_code(session, "owner_A").code

    service.handle_update(session, _text_update(777, f"/start {code}"))

    link = session.get(TelegramLink, 777)
    assert link.owner_id == "owner_A"


def test_two_chats_linked_to_different_owners_stay_independent(session, mock_send):
    code_a = service.create_link_code(session, "owner_A").code
    code_b = service.create_link_code(session, "owner_B").code

    service.handle_update(session, _text_update(111, f"/start {code_a}"))
    service.handle_update(session, _text_update(222, f"/start {code_b}"))

    assert session.get(TelegramLink, 111).owner_id == "owner_A"
    assert session.get(TelegramLink, 222).owner_id == "owner_B"


# --- is_linked / status -------------------------------------------------------------------


def test_is_linked_true_for_linked_owner(session):
    session.add(TelegramLink(telegram_chat_id=555, owner_id=_TEST_USER))
    session.commit()

    assert service.is_linked(session, _TEST_USER) is True


def test_is_linked_false_for_unlinked_owner(session):
    assert service.is_linked(session, _TEST_USER) is False


def test_is_linked_owner_scoped(session):
    # Owner B's link must not make owner A appear linked.
    session.add(TelegramLink(telegram_chat_id=555, owner_id="owner_B"))
    session.commit()

    assert service.is_linked(session, "owner_B") is True
    assert service.is_linked(session, _TEST_USER) is False


def test_status_endpoint_true_when_linked(session):
    session.add(TelegramLink(telegram_chat_id=555, owner_id=_TEST_USER))
    session.commit()
    client = TestClient(app)

    resp = client.get("/telegram/status")

    assert resp.status_code == 200
    assert resp.json() == {"linked": True}


def test_status_endpoint_false_when_unlinked():
    client = TestClient(app)

    resp = client.get("/telegram/status")

    assert resp.status_code == 200
    assert resp.json() == {"linked": False}


# --- HTTP: link endpoint + webhook security ---------------------------------------------


def test_link_endpoint_returns_code_and_deep_link():
    client = TestClient(app)
    resp = client.post("/telegram/link")

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"]
    assert body["deep_link"].endswith(body["code"])


def test_webhook_secret_mismatch_returns_403_and_processes_nothing(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "expected-secret")
    spy = Mock()
    monkeypatch.setattr(service, "handle_update", spy)
    client = TestClient(app)

    resp = client.post(
        "/telegram/webhook",
        json=_text_update(555, "hi"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert resp.status_code == 403
    spy.assert_not_called()


def test_webhook_secret_match_processes_update(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "expected-secret")
    spy = Mock()
    monkeypatch.setattr(service, "handle_update", spy)
    client = TestClient(app)

    resp = client.post(
        "/telegram/webhook",
        json=_text_update(555, "hi"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
    )

    assert resp.status_code == 200
    spy.assert_called_once()


def test_webhook_unset_secret_processes_in_dev(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", None)
    spy = Mock()
    monkeypatch.setattr(service, "handle_update", spy)
    client = TestClient(app)

    resp = client.post("/telegram/webhook", json=_text_update(555, "hi"))

    assert resp.status_code == 200
    spy.assert_called_once()


def test_webhook_malformed_body_is_200_noop(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", None)
    spy = Mock()
    monkeypatch.setattr(service, "handle_update", spy)
    client = TestClient(app)

    resp = client.post(
        "/telegram/webhook", content=b"not json", headers={"Content-Type": "application/json"}
    )

    assert resp.status_code == 200
    spy.assert_not_called()


def test_webhook_send_failure_is_swallowed_to_200(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", None)
    monkeypatch.setattr(
        service, "handle_update", Mock(side_effect=telegram_api.TelegramApiError("down"))
    )
    client = TestClient(app)

    resp = client.post("/telegram/webhook", json=_text_update(555, "hi"))

    assert resp.status_code == 200
    assert resp.json()["status"] == "send_failed"


# --- telegram_api.send_message ----------------------------------------------------------


def test_send_message_success(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "123:ABC")
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return Mock(raise_for_status=Mock())

    monkeypatch.setattr(telegram_api.httpx, "post", fake_post)

    telegram_api.send_message(555, "hello")

    assert captured["url"].endswith("/bot123:ABC/sendMessage")
    assert captured["json"] == {"chat_id": 555, "text": "hello"}


def test_send_message_api_failure_raises_telegram_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "123:ABC")

    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(telegram_api.httpx, "post", fake_post)

    with pytest.raises(telegram_api.TelegramApiError):
        telegram_api.send_message(555, "hello")


def test_send_message_missing_token_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", None)

    with pytest.raises(RuntimeError):
        telegram_api.send_message(555, "hello")


def test_send_message_truncates_over_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "123:ABC")
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return Mock(raise_for_status=Mock())

    monkeypatch.setattr(telegram_api.httpx, "post", fake_post)

    telegram_api.send_message(555, "y" * 9000)

    assert len(captured["json"]["text"]) == telegram_api.MAX_MESSAGE_LENGTH
