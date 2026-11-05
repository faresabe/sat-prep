"""
test_routing.py — pure function tests for the routing algorithm.
No DB, no async, no fixtures needed.
"""
from decimal import Decimal

import pytest

from app.modules.attempts.routing import (
    compute_weighted_score,
    decide_level,
    route,
    DEFAULT_THRESHOLD,
)


def test_weighted_score_all_correct():
    score = compute_weighted_score(
        correct_easy=5, correct_medium=5, correct_hard=5,
        total_easy=5,   total_medium=5,   total_hard=5,
    )
    assert score == Decimal("1.0000")


def test_weighted_score_all_wrong():
    score = compute_weighted_score(
        correct_easy=0, correct_medium=0, correct_hard=0,
        total_easy=5,   total_medium=5,   total_hard=5,
    )
    assert score == Decimal("0.0000")


def test_weighted_score_zero_denominator():
    score = compute_weighted_score(
        correct_easy=0, correct_medium=0, correct_hard=0,
        total_easy=0,   total_medium=0,   total_hard=0,
    )
    assert score == Decimal("0.0000")


def test_weighted_score_partial():
    # 3 easy correct (weight 1) + 0 medium + 0 hard, out of 5 easy + 5 medium + 5 hard
    # numerator = 3*1 = 3, denominator = 5*1 + 5*2 + 5*3 = 30
    score = compute_weighted_score(
        correct_easy=3, correct_medium=0, correct_hard=0,
        total_easy=5,   total_medium=5,   total_hard=5,
    )
    assert score == Decimal("0.1000")


def test_weighted_score_hard_weighted():
    # All hard correct: numerator = 5*3 = 15, denominator = 0 + 0 + 5*3 = 15
    score = compute_weighted_score(
        correct_easy=0, correct_medium=0, correct_hard=5,
        total_easy=0,   total_medium=0,   total_hard=5,
    )
    assert score == Decimal("1.0000")


def test_decide_level_hard():
    assert decide_level(Decimal("0.65")) == "hard"
    assert decide_level(Decimal("1.0000")) == "hard"
    assert decide_level(Decimal("0.7500")) == "hard"


def test_decide_level_easy():
    assert decide_level(Decimal("0.64")) == "easy"
    assert decide_level(Decimal("0.0000")) == "easy"
    assert decide_level(Decimal("0.5000")) == "easy"


def test_decide_level_custom_threshold():
    assert decide_level(Decimal("0.50"), threshold=Decimal("0.50")) == "hard"
    assert decide_level(Decimal("0.49"), threshold=Decimal("0.50")) == "easy"


def test_route_returns_all_fields():
    result = route(
        correct_easy=3, correct_medium=2, correct_hard=1,
        total_easy=5,   total_medium=5,   total_hard=5,
    )
    assert "weighted_score" in result
    assert "threshold" in result
    assert result["chosen_level"] in ("easy", "hard")
    assert result["algorithm_version"] == "weighted_v1"


def test_route_hard_path():
    result = route(
        correct_easy=5, correct_medium=5, correct_hard=5,
        total_easy=5,   total_medium=5,   total_hard=5,
    )
    assert result["chosen_level"] == "hard"


def test_route_easy_path():
    result = route(
        correct_easy=0, correct_medium=0, correct_hard=0,
        total_easy=5,   total_medium=5,   total_hard=5,
    )
    assert result["chosen_level"] == "easy"
