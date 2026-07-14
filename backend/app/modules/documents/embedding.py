"""Cohere embeddings for document chunks.

`input_type="search_document"` is the asymmetric-retrieval side for content being
indexed; a future Ask endpoint must embed the user's question with
`input_type="search_query"` instead — Cohere's retrieval quality depends on getting
this right on both sides, so the value here is deliberate, not incidental.

Two distinct failure modes, handled differently on purpose:
- `COHERE_API_KEY` unset is a deployment/config mistake — raises a bare `RuntimeError`
  at the point of use (same pattern as `app/core/db.py` and `app/core/auth.py`) so it
  fails loudly instead of masquerading as a per-document data problem.
- Everything else (rate limits, network errors, API errors) is a per-request failure —
  wrapped in `EmbeddingError` so callers can catch one exception type and degrade
  gracefully (mark the document `failed`) instead of crashing the request.
"""

from __future__ import annotations

import cohere

from app.core.config import get_settings

EMBEDDING_MODEL = "embed-multilingual-v3.0"
EMBEDDING_DIM = 1024


class EmbeddingError(Exception):
    """Raised when Cohere can't produce embeddings for the given texts."""


def _get_client() -> cohere.Client:
    settings = get_settings()
    if not settings.cohere_api_key:
        raise RuntimeError(
            "COHERE_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return cohere.Client(settings.cohere_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts as search documents, one 1024-dim vector per input text,
    in the same order. `batching=True` lets the Cohere SDK split large batches across
    multiple requests itself (its embed endpoint caps texts per call).
    """
    if not texts:
        return []

    client = _get_client()
    try:
        response = client.embed(
            texts=texts,
            model=EMBEDDING_MODEL,
            input_type="search_document",
            batching=True,
        )
    except Exception as exc:
        raise EmbeddingError(f"Cohere embedding request failed: {exc}") from exc

    embeddings = list(response.embeddings)
    if any(len(vector) != EMBEDDING_DIM for vector in embeddings):
        raise EmbeddingError(
            f"Cohere returned vectors of unexpected dimension (expected {EMBEDDING_DIM})"
        )
    return embeddings
