"""
test_grading.py — unit tests for _parse_numeric and grading logic.

Pure Python tests — no DB connection required for _parse_numeric.
"""
from decimal import Decimal

import pytest

from app.modules.attempts.grading import _parse_numeric


@pytest.mark.parametrize("raw,expected", [
    ("5",    Decimal("5")),
    ("5.0",  Decimal("5.0")),
    (".5",   Decimal(".5")),
    ("0.5",  Decimal("0.5")),
    ("-3",   Decimal("-3")),
    ("1/2",  Decimal("0.5")),
    ("-7/8", Decimal("-0.875")),
    ("",     None),
    (None,   None),
    ("abc",  None),
    ("1/0",  None),  # division by zero
])
def test_parse_numeric(raw, expected):
    result = _parse_numeric(raw)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert abs(result - expected) <= Decimal("0.0001")


def test_parse_numeric_comma_stripped():
    # The function strips commas (e.g. "1,000")
    result = _parse_numeric("1,000")
    assert result == Decimal("1000")
