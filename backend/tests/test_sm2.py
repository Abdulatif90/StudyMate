"""Unit tests for app.modules.flashcards.sm2 — the pure SM-2 scheduling algorithm.
`now` is always passed in explicitly (never wall-clock), so every assertion here is
deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.flashcards.sm2 import (
    DEFAULT_EASE_FACTOR,
    MIN_EASE_FACTOR,
    ReviewState,
    review,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_NEW_CARD = ReviewState(repetitions=0, ease_factor=DEFAULT_EASE_FACTOR, interval_days=0)


def test_first_successful_review_sets_interval_to_one_day():
    result = review(4, _NEW_CARD, _NOW)
    assert result.repetitions == 1
    assert result.interval_days == 1
    assert result.due_at == _NOW + timedelta(days=1)


def test_second_successful_review_sets_interval_to_six_days():
    after_first = review(4, _NEW_CARD, _NOW)
    state = ReviewState(
        repetitions=after_first.repetitions,
        ease_factor=after_first.ease_factor,
        interval_days=after_first.interval_days,
    )
    result = review(4, state, _NOW)
    assert result.repetitions == 2
    assert result.interval_days == 6


def test_third_successful_review_scales_by_ease_factor():
    # repetitions=2, interval=6, ease=2.5 -> next interval = round(6 * 2.5) = 15
    state = ReviewState(repetitions=2, ease_factor=2.5, interval_days=6)
    result = review(4, state, _NOW)
    assert result.repetitions == 3
    assert result.interval_days == 15


def test_grade_below_three_resets_repetitions_and_interval():
    # an established card with a long interval that then lapses
    state = ReviewState(repetitions=5, ease_factor=2.3, interval_days=40)
    result = review(2, state, _NOW)
    assert result.repetitions == 0
    assert result.interval_days == 1
    assert result.due_at == _NOW + timedelta(days=1)


@pytest.mark.parametrize("grade", [0, 1, 2])
def test_any_lapse_grade_resets_the_same_way(grade):
    state = ReviewState(repetitions=3, ease_factor=2.0, interval_days=10)
    result = review(grade, state, _NOW)
    assert result.repetitions == 0
    assert result.interval_days == 1


def test_lapse_decrements_ease_but_does_not_reset_it():
    # the classic SM-2 bug: conflating "reset progress" with "reset ease". A lapse must
    # only nudge ease down by the formula, not slam it back to the 2.5 default.
    state = ReviewState(repetitions=4, ease_factor=2.4, interval_days=20)
    result = review(2, state, _NOW)
    assert result.repetitions == 0  # progress reset
    expected_ease = 2.4 + (0.1 - 3 * (0.08 + 3 * 0.02))
    assert result.ease_factor == pytest.approx(expected_ease)
    assert result.ease_factor != DEFAULT_EASE_FACTOR
    assert result.ease_factor != 2.4  # it did change, just not reset


def test_perfect_grade_increases_ease_factor():
    result = review(5, ReviewState(repetitions=1, ease_factor=2.5, interval_days=6), _NOW)
    assert result.ease_factor > 2.5
    assert result.ease_factor == pytest.approx(2.6)


def test_grade_four_leaves_ease_factor_unchanged():
    # grade 4 is the formula's exact zero-crossing: 0.1 - 1*(0.08 + 1*0.02) == 0
    result = review(4, ReviewState(repetitions=1, ease_factor=2.5, interval_days=6), _NOW)
    assert result.ease_factor == pytest.approx(2.5)


def test_repeated_low_grades_floor_ease_factor_at_1_3():
    state = ReviewState(repetitions=0, ease_factor=DEFAULT_EASE_FACTOR, interval_days=0)
    for _ in range(20):
        result = review(0, state, _NOW)
        state = ReviewState(
            repetitions=result.repetitions,
            ease_factor=result.ease_factor,
            interval_days=result.interval_days,
        )
    assert state.ease_factor == MIN_EASE_FACTOR  # floored, never below


def test_ease_factor_never_drops_below_the_floor_in_a_single_review():
    # start already near the floor and take the worst possible grade
    state = ReviewState(repetitions=2, ease_factor=1.35, interval_days=10)
    result = review(0, state, _NOW)
    assert result.ease_factor >= MIN_EASE_FACTOR


@pytest.mark.parametrize("grade", [-1, 6, 100, -100])
def test_out_of_range_grade_raises(grade):
    with pytest.raises(ValueError, match="0 and 5"):
        review(grade, _NEW_CARD, _NOW)


def test_due_date_is_now_plus_interval_days():
    state = ReviewState(repetitions=2, ease_factor=2.0, interval_days=10)
    result = review(5, state, _NOW)
    assert result.due_at == _NOW + timedelta(days=result.interval_days)


def test_review_does_not_mutate_the_input_state():
    state = ReviewState(repetitions=1, ease_factor=2.5, interval_days=6)
    review(5, state, _NOW)
    assert state.repetitions == 1
    assert state.ease_factor == 2.5
    assert state.interval_days == 6
