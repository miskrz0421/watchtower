"""Tests for interval parsing."""

from __future__ import annotations

from datetime import timedelta

import pytest

from watchtower import ConfigError
from watchtower.config import parse_interval


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30s", timedelta(seconds=30)),
        ("1s", timedelta(seconds=1)),
        ("15m", timedelta(minutes=15)),
        ("1m", timedelta(minutes=1)),
        ("2h", timedelta(hours=2)),
        ("24h", timedelta(hours=24)),
        ("1d", timedelta(days=1)),
        ("7d", timedelta(days=7)),
        ("365d", timedelta(days=365)),
    ],
)
def test_parse_valid_intervals(text: str, expected: timedelta) -> None:
    """Test that valid interval strings produce correct timedeltas."""
    assert parse_interval(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "0s",
        "0m",
        "0h",
        "0d",
        "00s",
        "-5s",
        "-15m",
        "-1h",
        "-2d",
        "1.5m",
        "0.5h",
        "30",
        "15ms",
        "2w",
        "10sec",
        "5min",
        "abc",
        "",
        " 15m",
        "15m ",
        "15 m",
        "15m\n",
    ],
)
def test_parse_invalid_intervals_raise_config_error(text: str) -> None:
    """Test that invalid interval formats and non-positive numbers raise ConfigError."""
    with pytest.raises(ConfigError):
        parse_interval(text)


def test_parse_interval_overflow_raises_config_error() -> None:
    """Test that an interval that exceeds timedelta limits raises ConfigError."""
    with pytest.raises(ConfigError, match=r"Interval '9999999999d' is too long"):
        parse_interval("9999999999d")


def test_parse_non_string_raises_config_error() -> None:
    """Test that non-string interval input raises ConfigError."""
    with pytest.raises(ConfigError, match="Interval must be text"):
        parse_interval(15)  # type: ignore[arg-type]
