"""Tests for source parsing utilities."""

from __future__ import annotations

import pytest

from watchtower.sources import parse_price


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 999 zł", 2999.0),
        ("2\u00a0999 zł", 2999.0),
        ("2\u202f999 zł", 2999.0),
        ("800 zł", 800.0),
        ("1 250 000 zł", 1250000.0),
        ("1.250.000 zł", 1250000.0),
        ("2 999,99 zł", 2999.99),
        ("2,999.99 zł", 2999.99),
        ("2999.50 zł", 2999.5),
        ("2 999 zł/mies.", 2999.0),
        ("Flat 2, 2 800 zł", 2800.0),
        ("50 m², 2 800 zł", 2800.0),
        ("3 pokoje 2800 zł", 2800.0),
        ("2 rooms, 45 m2, 3 100 PLN", 3100.0),
        ("Price: € 1 200", 1200.0),
        ("5 zleceń, 2 000 zł", 2000.0),
        ("Flat 2, 2 800", 2.0),  # no currency: the first number wins
        ("No price", None),
        ("Price on request", None),
        ("", None),
    ],
)
def test_parse_price(text: str, expected: float | None) -> None:
    """Test price parsing with different separators and missing prices."""
    assert parse_price(text) == expected
