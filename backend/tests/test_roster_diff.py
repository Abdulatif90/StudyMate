"""Pure roster-diff unit tests — Phase 5 (assignment submission roster).

`build_roster_diff` is the I/O-free core of the roster feature: given an org's member ids
(from Clerk) and an assignment's existing submissions (from the DB), it splits members into
who HAS and who HASN'T submitted. These tests exercise it directly — no app, no DB, no
Clerk, no network — because the diff logic is the security- and correctness-critical part
and must be provable in isolation.
"""

from __future__ import annotations

import uuid

from app.modules.assignments.models import AssignmentSubmission
from app.modules.assignments.service import build_roster_diff

_ASSIGNMENT_ID = uuid.uuid4()


def _submission(owner_id: str, score: int | None = None) -> AssignmentSubmission:
    """A plain in-memory submission row (never persisted — the diff needs no session)."""
    return AssignmentSubmission(assignment_id=_ASSIGNMENT_ID, owner_id=owner_id, score=score)


def test_members_ABC_submission_A():
    submitted, not_submitted = build_roster_diff(["A", "B", "C"], [_submission("A", score=90)])
    assert [m.user_id for m in submitted] == ["A"]
    assert submitted[0].submitted is True
    assert submitted[0].score == 90
    assert [m.user_id for m in not_submitted] == ["B", "C"]
    assert all(m.submitted is False for m in not_submitted)
    assert all(m.score is None for m in not_submitted)


def test_empty_members():
    # No members at all → both lists empty, even if (impossibly) submissions existed.
    submitted, not_submitted = build_roster_diff([], [])
    assert submitted == []
    assert not_submitted == []


def test_empty_members_with_only_ex_member_submitter():
    # Nobody is currently a member, but someone submitted then left → surfaced as an
    # ex-member submitter, never silently dropped.
    submitted, not_submitted = build_roster_diff([], [_submission("X", score=42)])
    assert [m.user_id for m in submitted] == ["X"]
    assert submitted[0].score == 42
    assert not_submitted == []


def test_all_submitted():
    submitted, not_submitted = build_roster_diff(["A", "B"], [_submission("A"), _submission("B")])
    assert {m.user_id for m in submitted} == {"A", "B"}
    assert not_submitted == []


def test_none_submitted():
    submitted, not_submitted = build_roster_diff(["A", "B", "C"], [])
    assert submitted == []
    assert [m.user_id for m in not_submitted] == ["A", "B", "C"]


def test_submitter_not_in_member_list_is_appended_gracefully():
    # Members {A, B}; submissions from A (a member) and X (left the org). X must appear in
    # `submitted` (result preserved), never in `not_submitted`, and not affect member rows.
    submitted, not_submitted = build_roster_diff(
        ["A", "B"], [_submission("A", score=70), _submission("X", score=55)]
    )
    # Member submitters first (member order), then ex-member submitters (sorted).
    assert [m.user_id for m in submitted] == ["A", "X"]
    assert {m.user_id: m.score for m in submitted} == {"A": 70, "X": 55}
    assert [m.user_id for m in not_submitted] == ["B"]


def test_duplicate_member_id_deduped():
    submitted, not_submitted = build_roster_diff(["A", "A", "B"], [_submission("A")])
    assert [m.user_id for m in submitted] == ["A"]  # A once, not twice
    assert [m.user_id for m in not_submitted] == ["B"]


def test_member_order_preserved():
    _, not_submitted = build_roster_diff(["C", "A", "B"], [])
    assert [m.user_id for m in not_submitted] == ["C", "A", "B"]
