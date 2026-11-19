"""Clocks: the only place the engine gets the time from (see ADR-008)."""

from __future__ import annotations

import threading
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

    def wait(self, seconds: float | None, wake: threading.Event) -> None:
        """Wait before the next look at the time, or less if `wake` is set.

        Args:
            seconds: How long to wait at most, never negative; None waits until
                `wake` is set.
            wake: Event another thread sets to end the wait early.
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

    def wait(self, seconds: float | None, wake: threading.Event) -> None:
        """Block the calling thread until the time is up or `wake` is set.

        Args:
            seconds: How long to block at most; None blocks until `wake` is set.
            wake: Event another thread sets to end the wait early.
        """
        wake.wait(seconds)


class FakeClock:
    """Clock for tests: time moves only when the test or `wait` moves it."""

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

    def wait(self, seconds: float | None, wake: threading.Event) -> None:
        """Move the clock forward instead of waiting, unless `wake` is already set.

        Args:
            seconds: How far to move the clock; None leaves it where it is,
                since nothing else would move the fake time.
            wake: If set, the clock is not moved, as the real wait would end at once.
        """
        if seconds is not None and not wake.is_set():
            self.advance(seconds)

    def advance(self, seconds: float) -> None:
        """Move the clock forward from a test.

        Args:
            seconds: How far to move the clock.
        """
        self._now += timedelta(seconds=seconds)
