"""Unit tests for app.modules.documents.rrf.reciprocal_rank_fusion — pure fusion logic,
no DB. This is where the "how the two hybrid arms combine" behavior is pinned down; the
live test in test_search.py covers the real Postgres FTS + vector + fuse pipeline.
"""

from __future__ import annotations

from app.modules.documents.rrf import RRF_K, reciprocal_rank_fusion


def _order(fused: list[tuple[str, float]]) -> list[str]:
    return [item for item, _score in fused]


def test_single_list_preserves_order():
    fused = reciprocal_rank_fusion([["a", "b", "c"]])
    assert _order(fused) == ["a", "b", "c"]
    # scores strictly decrease with rank: 1/(k+1) > 1/(k+2) > 1/(k+3)
    scores = [score for _item, score in fused]
    assert scores == sorted(scores, reverse=True)


def test_item_in_both_lists_outranks_item_in_one():
    # "b" is mid-rank in both arms; "a" is only #1 in the first arm.
    vector = ["a", "b", "c"]
    fts = ["d", "b", "e"]
    fused = _order(reciprocal_rank_fusion([vector, fts]))
    # b appears in both (1/(k+2) + 1/(k+2)) and beats a (only 1/(k+1))
    assert fused[0] == "b"
    assert set(fused) == {"a", "b", "c", "d", "e"}


def test_agreed_top_item_wins():
    # both arms rank "x" first — it must come out on top.
    fused = _order(reciprocal_rank_fusion([["x", "y"], ["x", "z"]]))
    assert fused[0] == "x"


def test_one_empty_arm_falls_back_to_the_other():
    fused = reciprocal_rank_fusion([["a", "b", "c"], []])
    assert _order(fused) == ["a", "b", "c"]


def test_both_arms_empty():
    assert reciprocal_rank_fusion([[], []]) == []


def test_no_arms():
    assert reciprocal_rank_fusion([]) == []


def test_ties_break_by_first_appearance_order():
    # "a" (rank 1 in arm 1) and "b" (rank 1 in arm 2) have identical fused scores
    # (1/(k+1) each). Deterministic tie-break = first appearance across the input lists,
    # so "a" (seen first) precedes "b".
    fused = _order(reciprocal_rank_fusion([["a"], ["b"]]))
    assert fused == ["a", "b"]


def test_scores_use_the_rrf_formula_with_k():
    # a lone item at rank 1 scores exactly 1/(k+1).
    [(item, score)] = reciprocal_rank_fusion([["only"]])
    assert item == "only"
    assert score == 1.0 / (RRF_K + 1)


def test_k_constant_dampens_rank_influence():
    # Larger k flattens the gap between rank 1 and rank 2; smaller k sharpens it.
    lists = [["first", "second"]]
    small_k = dict(reciprocal_rank_fusion(lists, k=1))
    large_k = dict(reciprocal_rank_fusion(lists, k=1000))
    small_gap = small_k["first"] - small_k["second"]
    large_gap = large_k["first"] - large_k["second"]
    assert small_gap > large_gap
