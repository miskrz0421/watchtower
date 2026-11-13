"""Scheduler deciding which watcher runs when (Mediator pattern)."""

from __future__ import annotations

from datetime import datetime

from watchtower.core.clock import Clock
from watchtower.core.watcher import Watcher


class Scheduler:
    """Runs watchers at their intervals, one check at a time (see ADR-007).

    Keeps the next due time of every watcher. All time comes from the clock,
    so tests drive the scheduler with a FakeClock and never sleep (ADR-008).
    """

    def __init__(self, clock: Clock | None = None) -> None:
        """Initialize Scheduler.

        Args:
            clock: Source of time; None means the real SystemClock.
        """
        raise NotImplementedError

    def add(self, watcher: Watcher) -> None:
        """Start scheduling a watcher; its first check is due immediately.

        Args:
            watcher: Watcher to run every `watcher.interval`.

        Raises:
            ValueError: If a watcher with the same name was already added.
        """
        raise NotImplementedError

    def next_due(self) -> datetime | None:
        """Return when the next check is due.

        Returns:
            The earliest due time, or None if there are no watchers.
        """
        raise NotImplementedError

    def run_pending(self) -> int:
        """Check every watcher that is due now, one after another.

        A failing check is logged and does not stop the others; the watcher
        is tried again after its interval.

        Returns:
            Number of watchers that were checked.
        """
        raise NotImplementedError

    def run_forever(self) -> None:
        """Run due watchers and sleep until the next one, until `stop` is called."""
        raise NotImplementedError

    def stop(self) -> None:
        """Make `run_forever` return after the check that is running."""
        raise NotImplementedError
