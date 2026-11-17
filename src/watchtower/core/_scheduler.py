"""Scheduler deciding which watcher runs when (Mediator pattern)."""

from __future__ import annotations

import logging
import queue
from datetime import datetime

from watchtower._errors import WatchtowerError
from watchtower.core._clock import Clock, SystemClock
from watchtower.core._commands import CheckNow, Command, Pause, ReloadConfig, Resume
from watchtower.core._states import WatcherStatus
from watchtower.core._watcher import Watcher

_logger = logging.getLogger(__name__)


class Scheduler:
    """Runs watchers at their intervals, one check at a time (see ADR-007).

    Keeps the next due time of every watcher. All time comes from the clock,
    so tests drive the scheduler with a FakeClock and never sleep (ADR-008).
    Other threads control it only through `submit` (ADR-023).
    """

    def __init__(self, clock: Clock | None = None) -> None:
        """Initialize Scheduler.

        Args:
            clock: Source of time; None means the real SystemClock.
        """
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._watchers: dict[str, Watcher] = {}
        self._due: dict[str, datetime] = {}
        self._commands: queue.SimpleQueue[Command] = queue.SimpleQueue()
        self._stop_requested = False

    def add(self, watcher: Watcher) -> None:
        """Start scheduling a watcher; its first check is due immediately.

        Args:
            watcher: Watcher to run every `watcher.interval`.

        Raises:
            ValueError: If a watcher with the same name was already added.
        """
        if watcher.name in self._watchers:
            msg = f"A watcher named {watcher.name!r} is already scheduled"
            raise ValueError(msg)
        self._watchers[watcher.name] = watcher
        self._due[watcher.name] = self._clock.now()

    def submit(self, command: Command) -> None:
        """Queue a command; it is applied at the start of the next `run_pending`.

        Safe to call from any thread: this is how the GUI controls the engine.

        Args:
            command: Command to apply.
        """
        self._commands.put(command)

    def statuses(self) -> list[WatcherStatus]:
        """Return the state of every watcher, in the order they were added.

        The GUI calls it once, before the scheduler starts in its own thread,
        and then follows the events (see ADR-023).

        Returns:
            One status per watcher.
        """
        raise NotImplementedError

    def next_due(self) -> datetime | None:
        """Return when the next check is due.

        Returns:
            The earliest due time, or None if there are no watchers.
        """
        return min(self._due.values(), default=None)

    def run_pending(self) -> int:
        """Apply the submitted commands, then check every watcher that is due now.

        Watchers are checked one after another. A failing check is logged and
        does not stop the others; the watcher is tried again after its interval.

        Returns:
            Number of watchers that were checked.
        """
        self._apply_commands()
        now = self._clock.now()
        due = [watcher for name, watcher in self._watchers.items() if self._due[name] <= now]
        for watcher in due:
            self._check(watcher)
        return len(due)

    def run_forever(self) -> None:
        """Run due watchers and sleep until the next one, until `stop` is called.

        Returns at once if no watcher was added.
        """
        self._stop_requested = False
        while self._watchers and not self._stop_requested:
            self._clock.sleep(self._seconds_until_next_due())
            self.run_pending()

    def stop(self) -> None:
        """Make `run_forever` return after the check that is running."""
        self._stop_requested = True

    def _apply_commands(self) -> None:
        """Apply every submitted command, oldest first."""
        while not self._commands.empty():
            self._apply(self._commands.get())

    def _apply(self, command: Command) -> None:
        """Apply one command.

        Args:
            command: Command taken from the queue.
        """
        match command:
            case CheckNow(watcher_name=name):
                self._check_now(name)
            case Pause() | Resume() | ReloadConfig():
                raise NotImplementedError

    def _check_now(self, name: str) -> None:
        """Make a watcher due at once; an unknown name is logged and ignored.

        Args:
            name: Name of the watcher to check.
        """
        if name in self._due:
            self._due[name] = self._clock.now()
        else:
            _logger.warning("Cannot check %r now: no watcher has that name", name)

    def _check(self, watcher: Watcher) -> None:
        """Run one check and set the watcher's next due time.

        The next check is due one interval after this one ends, whether it
        succeeded or not. A WatchtowerError is an expected failure that the
        watcher already publishes on its event bus, so it is only logged at
        DEBUG; any other exception is a bug and is logged with its traceback.

        Args:
            watcher: Watcher to check.
        """
        try:
            watcher.check_once()
        except WatchtowerError as err:
            _logger.debug("Watcher %r failed: %s", watcher.name, err)
        except Exception:
            _logger.exception("Unexpected error in watcher %r", watcher.name)
        self._due[watcher.name] = self._clock.now() + watcher.interval

    def _seconds_until_next_due(self) -> float:
        """Return how long to sleep before the earliest due check.

        Returns:
            Seconds until the next check; 0 if one is already due.
        """
        wait = min(self._due.values()) - self._clock.now()
        return max(wait.total_seconds(), 0.0)
