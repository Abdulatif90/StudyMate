"""Reciprocal Rank Fusion — combine several independently-ranked candidate lists into
one fused ranking.

Hybrid retrieval runs two arms over the same chunks: a vector (cosine-distance) arm and
a lexical (Postgres full-text) arm. Their scores live on completely different scales
(cosine distance vs. `ts_rank`), so they can't be added directly. RRF sidesteps that by
fusing on **rank position**, not raw score: an item's fused score is the sum, across the
arms it appears in, of `1 / (k + rank)` (rank is 1-based). An item ranked highly by
either arm — or modestly by both — floats to the top; an item only one arm found still
contributes. This is what lets an exact keyword match the vector arm underweights get
surfaced.

`k` (default 60, the value from the original Cormack et al. RRF paper) damps the
influence of top ranks so a single arm's #1 can't completely dominate the fusion; larger
`k` flattens the contribution curve, smaller `k` sharpens it. Pure and DB-free so the
fusion logic is unit-testable without Postgres.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence

RRF_K = 60


def reciprocal_rank_fusion[T: Hashable](
    ranked_lists: Sequence[Sequence[T]], k: int = RRF_K
) -> list[tuple[T, float]]:
    """Fuse `ranked_lists` (each already ordered best-first) into a single ranking.
    Returns `(item, fused_score)` pairs, highest fused score first.

    Ties (equal fused score) are broken by first-appearance order across the input lists
    — deterministic for fixed inputs, since the accumulator dict preserves insertion
    order and the sort below is stable.
    """
    scores: dict[T, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
