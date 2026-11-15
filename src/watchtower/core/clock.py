"""Clocks: the only place the engine gets the time from (see ADR-008)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Source of the current time and of waiting."""

    def now(self) -> datetime:
        """Return the current time.

        Returns:
            The current time in UTC.
        """
        ...

    def sleep(self, seconds: float) -> None:
        """Wait before the next look at the time.

        Args:
            seconds: How long to wait; never negative.
        """
        ...


class SystemClock:
    """Clock backed by the real time of the computer."""

    def now(self) -> datetime:
        """Return the real current time.

        Returns:
            The current time in UTC.
        """
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        """Block the calling thread.

        Args:
            seconds: How long to block.
        """
        time.sleep(seconds)


class FakeClock:
    """Clock for tests: time moves only when the test or `sleep` moves it."""

    def __init__(self, start: datetime) -> None:
        """Initialize FakeClock.

        Args:
            start: Time the clock shows at first; must be timezone-aware.

        Raises:
            ValueError: If `start` has no time zone.
        """
        if start.tzinfo is None:
            msg = "FakeClock needs a timezone-aware start time"
            raise ValueError(msg)
        self._now = start

    def now(self) -> datetime:
        """Return the time the clock shows.

        Returns:
            The fake current time.
        """
        return self._now

    def sleep(self, seconds: float) -> None:
        """Move the clock forward instead of waiting.

        Args:
            seconds: How far to move the clock.
        """
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        """Move the clock forward from a test.

        Args:
            seconds: How far to move the clock.
        """
        self._now += timedelta(seconds=seconds)
