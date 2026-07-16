"""Cohere Rerank — narrows a wider vector-similarity candidate pool down to the final
top_n chunks that actually get sent to Claude (see `service._rerank_candidates`).

`rerank-v3.5` is Cohere's multilingual rerank model — the app is multilingual, an
English-only rerank model would degrade non-English subjects, same reasoning as
`embedding.EMBEDDING_MODEL` being `embed-multilingual-v3.0`.

Reuses `embedding._get_client` rather than duplicating the `COHERE_API_KEY` check —
one Cohere `Client` instance supports both `.embed()` and `.rerank()`, and both belong
to the same "missing key is a deployment mistake, bare `RuntimeError` at point of use"
family as `db.py`/`auth.py`/`llm.py`. Any other API/network failure is wrapped in
`RerankError` so `service._rerank_candidates` can catch it and fall back to the
pre-rerank vector-similarity order rather than failing the whole Ask request.
"""

from __future__ import annotations

from app.modules.documents.embedding import _get_client

RERANK_MODEL = "rerank-v3.5"


class RerankError(Exception):
    """Raised when Cohere can't rerank the given documents."""


def rerank(query: str, texts: list[str], top_n: int) -> list[tuple[int, float]]:
    """Rerank `texts` against `query`, returning up to `top_n` `(original_index,
    relevance_score)` pairs, most relevant first. `original_index` indexes back into
    `texts` — Cohere's response only carries positions, not the documents themselves
    (unless `return_documents=True`, which isn't needed here).
    """
    if not texts:
        return []

    client = _get_client()
    try:
        response = client.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=texts,
            top_n=min(top_n, len(texts)),
        )
    except Exception as exc:
        raise RerankError(f"Cohere rerank request failed: {exc}") from exc

    return [(result.index, result.relevance_score) for result in response.results]
