"""Unit tests for app.modules.documents.rerank — the Cohere *client* is mocked here
(not our own rerank wrapper), so these exercise rerank's own logic: the empty-list
short-circuit, the call shape, response-index mapping, and error wrapping.

See tests/test_search.py for _rerank_candidates (the higher-level piece that turns
these index/score pairs back into (DocumentChunk, score) results and handles the
RerankError fallback), with rerank itself mocked instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.documents import embedding
from app.modules.documents import rerank as rerank_module


@pytest.fixture(autouse=True)
def _fake_get_client(monkeypatch):
    # rerank.py reuses embedding._get_client directly (not its own copy) — patch it at
    # its point of use in rerank_module's namespace.
    monkeypatch.setattr(rerank_module, "_get_client", MagicMock())


def _fake_result(index: int, relevance_score: float):
    return SimpleNamespace(index=index, relevance_score=relevance_score)


def test_rerank_returns_empty_list_without_touching_cohere():
    assert rerank_module.rerank("query", [], top_n=5) == []
    rerank_module._get_client.assert_not_called()


def test_rerank_returns_index_score_pairs_from_cohere():
    fake_client = MagicMock()
    fake_client.rerank.return_value = SimpleNamespace(
        results=[_fake_result(1, 0.9), _fake_result(0, 0.2)]
    )
    rerank_module._get_client.return_value = fake_client

    result = rerank_module.rerank(
        "How do plants use sunlight?", ["volcanoes", "photosynthesis"], top_n=2
    )

    assert result == [(1, 0.9), (0, 0.2)]
    fake_client.rerank.assert_called_once_with(
        model=rerank_module.RERANK_MODEL,
        query="How do plants use sunlight?",
        documents=["volcanoes", "photosynthesis"],
        top_n=2,
    )


def test_rerank_caps_top_n_at_the_number_of_texts():
    fake_client = MagicMock()
    fake_client.rerank.return_value = SimpleNamespace(results=[_fake_result(0, 0.5)])
    rerank_module._get_client.return_value = fake_client

    rerank_module.rerank("query", ["only one text"], top_n=30)

    assert fake_client.rerank.call_args.kwargs["top_n"] == 1


def test_rerank_wraps_api_failures():
    fake_client = MagicMock()
    fake_client.rerank.side_effect = RuntimeError("network exploded")
    rerank_module._get_client.return_value = fake_client

    with pytest.raises(rerank_module.RerankError):
        rerank_module.rerank("query", ["a", "b"], top_n=2)


def test_rerank_reuses_embeddings_missing_key_error(monkeypatch):
    # Not mocking _get_client here (undoes the autouse fixture's monkeypatch by
    # re-patching it back to the real embedding._get_client) — proves rerank.py
    # actually reuses embedding's RuntimeError check rather than duplicating it.
    monkeypatch.setattr(rerank_module, "_get_client", embedding._get_client)
    monkeypatch.setattr(embedding, "get_settings", lambda: SimpleNamespace(cohere_api_key=None))

    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        rerank_module.rerank("query", ["a"], top_n=1)
