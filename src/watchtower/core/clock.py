"""Clocks: the only place the engine gets the time from (see ADR-008)."""

from __future__ import annotations

from datetime import datetime
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
        raise NotImplementedError

    def sleep(self, seconds: float) -> None:
        """Block the calling thread.

        Args:
            seconds: How long to block.
        """
        raise NotImplementedError


class FakeClock:
    """Clock for tests: time moves only when the test or `sleep` moves it."""

    def __init__(self, start: datetime) -> None:
        """Initialize FakeClock.

        Args:
            start: Time the clock shows at first; must be timezone-aware.
        """
        raise NotImplementedError

    def now(self) -> datetime:
        """Return the time the clock shows.

        Returns:
            The fake current time.
        """
        raise NotImplementedError

    def sleep(self, seconds: float) -> None:
        """Move the clock forward instead of waiting.

        Args:
            seconds: How far to move the clock.
        """
        raise NotImplementedError

    def advance(self, seconds: float) -> None:
        """Move the clock forward from a test.

        Args:
            seconds: How far to move the clock.
        """
        raise NotImplementedError
