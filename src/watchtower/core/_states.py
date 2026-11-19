"""Runtime states of a watcher (State pattern, see ADR-023)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar

from watchtower._events import WatcherState

_MAX_BACKOFF = timedelta(hours=1)
_FAILURES_BEFORE_DISABLED = 5


@dataclass(frozen=True)
class WatcherStatus:
    """What the GUI shows about one watcher."""

    name: str
    state: WatcherState
    interval: timedelta
    last_check: datetime | None


class State(ABC):
    """Decides when a watcher is checked next and which state follows a check."""

    kind: ClassVar[WatcherState]

    @abstractmethod
    def delay(self, interval: timedelta) -> timedelta | None:
        """Return how long to wait before the next check.

        Args:
            interval: The watcher's normal time between checks.

        Returns:
            The time to wait, or None if the watcher is not checked in this state.
        """

    @abstractmethod
    def after_success(self) -> State:
        """Return the state that follows a successful check.

        Returns:
            The next state.
        """

    @abstractmethod
    def after_failure(self) -> State:
        """Return the state that follows a failed check.

        Returns:
            The next state.
        """


class Active(State):
    """Checked every interval."""

    kind = WatcherState.ACTIVE

    def delay(self, interval: timedelta) -> timedelta | None:
        """Return the normal interval.

        Args:
            interval: The watcher's normal time between checks.

        Returns:
            The interval.
        """
        return interval

    def after_success(self) -> State:
        """Stay active.

        Returns:
            An Active state.
        """
        return self

    def after_failure(self) -> State:
        """Start backing off.

        Returns:
            A Backoff state after one failure.
        """
        return Backoff(failures=1)


class Paused(State):
    """Not checked until the user resumes it."""

    kind = WatcherState.PAUSED

    def delay(self, interval: timedelta) -> timedelta | None:
        """Return None: a paused watcher is not checked.

        Args:
            interval: The watcher's normal time between checks.

        Returns:
            None.
        """
        return None

    def after_success(self) -> State:
        """Stay paused; a check that was running when the user paused does not resume it.

        Returns:
            This state.
        """
        return self

    def after_failure(self) -> State:
        """Stay paused.

        Returns:
            This state.
        """
        return self


class Backoff(State):
    """Checked less often after failures: the wait doubles with each one, up to a cap."""

    kind = WatcherState.BACKOFF

    def __init__(self, failures: int) -> None:
        """Initialize Backoff.

        Args:
            failures: Number of failed checks in a row, at least 1.

        Raises:
            ValueError: If `failures` is less than 1.
        """
        if failures < 1:
            msg = f"Backoff needs at least one failure, got {failures}"
            raise ValueError(msg)
        self._failures = failures

    @property
    def failures(self) -> int:
        """Number of failed checks in a row."""
        return self._failures

    def delay(self, interval: timedelta) -> timedelta | None:
        """Return the interval doubled once per failure, at most one hour or the interval if longer.

        Args:
            interval: The watcher's normal time between checks.

        Returns:
            The time to wait.
        """
        doubled: timedelta = interval * 2**self._failures
        cap = max(_MAX_BACKOFF, interval)
        return min(doubled, cap)

    def after_success(self) -> State:
        """Recover.

        Returns:
            An Active state.
        """
        return Active()

    def after_failure(self) -> State:
        """Back off further, or give up after too many failures in a row.

        Returns:
            A Backoff state with one more failure, or Disabled.
        """
        failures = self._failures + 1
        return Disabled() if failures >= _FAILURES_BEFORE_DISABLED else Backoff(failures)


class Disabled(State):
    """Not checked after too many failures in a row; only Resume brings it back."""

    kind = WatcherState.DISABLED

    def delay(self, interval: timedelta) -> timedelta | None:
        """Return None: a disabled watcher is not checked.

        Args:
            interval: The watcher's normal time between checks.

        Returns:
            None.
        """
        return None

    def after_success(self) -> State:
        """Stay disabled.

        Returns:
            This state.
        """
        return self

    def after_failure(self) -> State:
        """Stay disabled.

        Returns:
            This state.
        """
        return self
