"""The SM-2 spaced-repetition scheduling algorithm — the canonical SuperMemo 2 formula,
applied one review at a time.

**Pure function, no DB, no I/O, no `datetime.now()` buried inside.** `now` is always
supplied by the caller (`service.review_flashcard`), never read here — that's what
makes every rule below deterministically unit-testable (a fixed `now` in → a fixed
`due_at` out) instead of depending on wall-clock time during tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# SuperMemo's own documented floor. Without it, repeated low grades drive `ease_factor`
# toward (or past) zero — the update formula below is unbounded below — which would
# shrink or invert future intervals instead of just slowing their growth.
MIN_EASE_FACTOR = 1.3

# A new card's starting ease — "average" difficulty, per the original SM-2 spec.
DEFAULT_EASE_FACTOR = 2.5

# SuperMemo's 0-5 quality scale: 3 is the pass/fail boundary. >=3 is a successful
# recall (advances the schedule); <3 is a lapse (resets it). 0-2 still distinguish
# *how* badly it was missed, but that distinction only feeds the ease-factor formula
# below, not the reset-vs-advance branch.
PASSING_GRADE = 3


@dataclass(frozen=True)
class ReviewState:
    """A flashcard's current spaced-repetition state — DB-shape-agnostic; the service
    maps this to/from `Flashcard` columns before/after calling `review`."""

    repetitions: int
    ease_factor: float
    interval_days: int


@dataclass(frozen=True)
class ReviewResult:
    """The next state after grading one review, plus the concrete next due date."""

    repetitions: int
    ease_factor: float
    interval_days: int
    due_at: datetime


def review(grade: int, state: ReviewState, now: datetime) -> ReviewResult:
    """Apply one review `grade` (0-5) to `state`, returning the next SM-2 state and its
    due date (`now + interval_days`). Raises `ValueError` for a grade outside 0-5 — the
    service must validate before this is ever called; a corrupted grade must never reach
    the schedule.
    """
    if not 0 <= grade <= 5:
        raise ValueError(f"grade must be between 0 and 5, got {grade}")

    if grade < PASSING_GRADE:
        # Lapse: SM-2 resets progress back to the first learning step, as if relearning
        # the card from scratch. Ease is NOT touched here — only decremented by the
        # unconditional formula below. Resetting both repetitions/interval *and* ease
        # together is the classic SM-2 bug: a card the learner has eased up over many
        # good reviews shouldn't lose that entire history to one slip.
        repetitions = 0
        interval_days = 1
    else:
        # Success: advance. SM-2's first two successful reviews use fixed intervals
        # (1 day, then 6 days) — they aren't derived from the ease factor, only later
        # repetitions are. From the third successful review on, the new interval is the
        # previous interval scaled by the ease factor (updated below in the same call),
        # which is what makes intervals grow geometrically for cards kept getting right.
        if state.repetitions == 0:
            interval_days = 1
        elif state.repetitions == 1:
            interval_days = 6
        else:
            interval_days = round(state.interval_days * state.ease_factor)
        repetitions = state.repetitions + 1

    # Ease-factor update — SM-2's canonical formula, applied on EVERY review (pass or
    # lapse alike), not only on successes: even a failing grade nudges ease down by a
    # bounded amount rather than the reset above wiping it out.
    ease_factor = state.ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    ease_factor = max(MIN_EASE_FACTOR, ease_factor)

    return ReviewResult(
        repetitions=repetitions,
        ease_factor=ease_factor,
        interval_days=interval_days,
        due_at=now + timedelta(days=interval_days),
    )
