"""Tests for the Inngest wiring — the event-send path (documents.service.
enqueue_document_processing) and its missing-key guard. The Inngest client is mocked;
no network. The job handler's actual work is covered via process_document in
tests/test_documents.py.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import inngest_client
from app.modules.documents import service as documents_service
from app.modules.documents.models import Document


def _fake_document() -> Document:
    return Document(
        subject_id=uuid.uuid4(),
        owner_id="user_abc",
        filename="notes.txt",
        content_type="text/plain",
    )


def test_require_event_key_raises_when_unset(monkeypatch):
    monkeypatch.setattr(
        inngest_client, "get_settings", lambda: SimpleNamespace(inngest_event_key=None)
    )
    with pytest.raises(RuntimeError, match="INNGEST_EVENT_KEY"):
        inngest_client.require_event_key()


def test_enqueue_raises_when_event_key_unset(monkeypatch):
    # Missing key must fail loudly at point of use, not silently drop the event and
    # leave the document stuck on pending (same pattern as db.py/embedding.py/llm.py).
    monkeypatch.setattr(
        inngest_client, "get_settings", lambda: SimpleNamespace(inngest_event_key=None)
    )
    with pytest.raises(RuntimeError, match="INNGEST_EVENT_KEY"):
        documents_service.enqueue_document_processing(_fake_document())


def test_enqueue_sends_document_uploaded_event(monkeypatch):
    monkeypatch.setattr(
        inngest_client, "get_settings", lambda: SimpleNamespace(inngest_event_key="test-key")
    )
    fake_client = MagicMock()
    monkeypatch.setattr(documents_service, "get_inngest_client", lambda: fake_client)

    document = _fake_document()
    documents_service.enqueue_document_processing(document)

    fake_client.send_sync.assert_called_once()
    event = fake_client.send_sync.call_args.args[0]
    assert event.name == documents_service.DOCUMENT_UPLOADED_EVENT
    assert event.data == {"document_id": str(document.id), "owner_id": document.owner_id}
