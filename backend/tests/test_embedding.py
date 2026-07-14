"""Unit tests for app.modules.documents.embedding — the Cohere *client* is mocked here
(not our own embed_texts wrapper), so these actually exercise embed_texts' own logic:
the empty-list short-circuit, the call shape, and both error-wrapping paths.

See tests/test_documents.py for the higher-level integration tests (embeddings stored
per chunk, tenant scoping) that exercise this through service.create_document with
embed_texts itself mocked instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.documents import embedding


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(
        embedding, "get_settings", lambda: SimpleNamespace(cohere_api_key="test-key")
    )


def test_embed_texts_returns_empty_list_without_touching_cohere(monkeypatch):
    client_cls = MagicMock()
    monkeypatch.setattr(embedding.cohere, "Client", client_cls)

    assert embedding.embed_texts([]) == []
    client_cls.assert_not_called()


def test_embed_texts_returns_vectors_from_cohere(monkeypatch):
    fake_client = MagicMock()
    fake_client.embed.return_value = SimpleNamespace(
        embeddings=[[0.1] * embedding.EMBEDDING_DIM, [0.2] * embedding.EMBEDDING_DIM]
    )
    monkeypatch.setattr(embedding.cohere, "Client", MagicMock(return_value=fake_client))

    result = embedding.embed_texts(["hello", "world"])

    assert result == [[0.1] * embedding.EMBEDDING_DIM, [0.2] * embedding.EMBEDDING_DIM]
    fake_client.embed.assert_called_once_with(
        texts=["hello", "world"],
        model=embedding.EMBEDDING_MODEL,
        input_type="search_document",
        batching=True,
    )


def test_embed_texts_wraps_api_failures(monkeypatch):
    fake_client = MagicMock()
    fake_client.embed.side_effect = RuntimeError("network exploded")
    monkeypatch.setattr(embedding.cohere, "Client", MagicMock(return_value=fake_client))

    with pytest.raises(embedding.EmbeddingError):
        embedding.embed_texts(["hello"])


def test_embed_texts_rejects_wrong_dimension_response(monkeypatch):
    fake_client = MagicMock()
    fake_client.embed.return_value = SimpleNamespace(embeddings=[[0.1, 0.2]])  # too short
    monkeypatch.setattr(embedding.cohere, "Client", MagicMock(return_value=fake_client))

    with pytest.raises(embedding.EmbeddingError):
        embedding.embed_texts(["hello"])


def test_embed_texts_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(embedding, "get_settings", lambda: SimpleNamespace(cohere_api_key=None))

    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        embedding.embed_texts(["hello"])


def test_embed_query_returns_a_single_vector(monkeypatch):
    fake_client = MagicMock()
    fake_client.embed.return_value = SimpleNamespace(embeddings=[[0.3] * embedding.EMBEDDING_DIM])
    monkeypatch.setattr(embedding.cohere, "Client", MagicMock(return_value=fake_client))

    result = embedding.embed_query("what is mitosis?")

    assert result == [0.3] * embedding.EMBEDDING_DIM
    # the asymmetric half of the model — must NOT be "search_document" like embed_texts
    fake_client.embed.assert_called_once_with(
        texts=["what is mitosis?"],
        model=embedding.EMBEDDING_MODEL,
        input_type="search_query",
        batching=True,
    )


def test_embed_query_wraps_api_failures(monkeypatch):
    fake_client = MagicMock()
    fake_client.embed.side_effect = RuntimeError("network exploded")
    monkeypatch.setattr(embedding.cohere, "Client", MagicMock(return_value=fake_client))

    with pytest.raises(embedding.EmbeddingError):
        embedding.embed_query("what is mitosis?")
