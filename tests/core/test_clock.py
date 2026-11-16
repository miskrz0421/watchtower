"""Tests for the clocks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from watchtower.core import FakeClock, SystemClock

_START = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def test_system_clock_shows_the_real_time_in_utc() -> None:
    """Test that SystemClock returns an aware UTC time close to the real one."""
    before = datetime.now(UTC)
    now = SystemClock().now()
    assert now.tzinfo is UTC
    assert before <= now <= datetime.now(UTC)


def test_system_clock_sleep_returns() -> None:
    """Test that SystemClock.sleep with zero seconds returns at once."""
    SystemClock().sleep(0)


def test_fake_clock_starts_at_the_given_time() -> None:
    """Test that FakeClock shows its start time until moved."""
    assert FakeClock(_START).now() == _START


def test_fake_clock_sleep_and_advance_move_the_time() -> None:
    """Test that sleep and advance both move the fake time instead of waiting."""
    clock = FakeClock(_START)
    clock.sleep(30)
    clock.advance(90)
    assert clock.now() == _START + timedelta(minutes=2)


def test_fake_clock_rejects_a_naive_start_time() -> None:
    """Test that a start time without a time zone is refused."""
    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(datetime(2026, 11, 16, 12, 0))
