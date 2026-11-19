"""Tests for the clocks."""

from __future__ import annotations

import threading
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


def test_system_clock_wait_returns_when_the_time_is_up() -> None:
    """Test that SystemClock.wait with zero seconds returns at once."""
    SystemClock().wait(0, threading.Event())


def test_system_clock_wait_ends_early_when_woken() -> None:
    """Test that a set wake event ends a long wait at once."""
    wake = threading.Event()
    wake.set()
    before = datetime.now(UTC)
    SystemClock().wait(60, wake)
    assert datetime.now(UTC) - before < timedelta(seconds=5)


def test_fake_clock_starts_at_the_given_time() -> None:
    """Test that FakeClock shows its start time until moved."""
    assert FakeClock(_START).now() == _START


def test_fake_clock_wait_and_advance_move_the_time() -> None:
    """Test that wait and advance both move the fake time instead of waiting."""
    clock = FakeClock(_START)
    clock.wait(30, threading.Event())
    clock.advance(90)
    assert clock.now() == _START + timedelta(minutes=2)


def test_fake_clock_does_not_move_when_woken() -> None:
    """Test that a set wake event ends the fake wait before the time moves."""
    clock = FakeClock(_START)
    wake = threading.Event()
    wake.set()
    clock.wait(30, wake)
    assert clock.now() == _START


def test_fake_clock_wait_without_limit_returns_at_once() -> None:
    """Test that waiting with no time limit leaves the fake time where it is."""
    clock = FakeClock(_START)
    clock.wait(None, threading.Event())
    assert clock.now() == _START


def test_fake_clock_rejects_a_naive_start_time() -> None:
    """Test that a start time without a time zone is refused."""
    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(datetime(2026, 11, 16, 12, 0))
