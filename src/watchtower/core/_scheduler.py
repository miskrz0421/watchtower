"""Scheduler deciding which watcher runs when (Mediator pattern)."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from watchtower._errors import WatchtowerError
from watchtower._events import ConfigReloaded, EventBus, WatcherStateChanged
from watchtower.core._clock import Clock, SystemClock
from watchtower.core._commands import CheckNow, Command, Pause, ReloadConfig, Resume
from watchtower.core._states import Active, Backoff, Paused, State, WatcherStatus
from watchtower.core._watcher import Watcher

_logger = logging.getLogger(__name__)


class Scheduler:
    """Runs watchers one check at a time, when their states say they are due (ADR-007, ADR-023)."""

    def __init__(
        self,
        clock: Clock | None = None,
        load_watchers: Callable[[], Sequence[Watcher]] | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize Scheduler.

        Args:
            clock: Source of time; None means the real SystemClock.
            load_watchers: Returns new watchers, each with its own name, for a
                ReloadConfig command; None means the watchers cannot be reloaded.
            event_bus: Bus to publish ConfigReloaded on, if any.
        """
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._load_watchers = load_watchers
        self._event_bus = event_bus
        self._watchers: dict[str, Watcher] = {}
        self._states: dict[str, State] = {}
        self._due: dict[str, datetime] = {}
        self._last_check: dict[str, datetime] = {}
        self._commands: queue.SimpleQueue[Command] = queue.SimpleQueue()
        self._wake = threading.Event()
        self._stop_requested = False

    def add(self, watcher: Watcher) -> None:
        """Start scheduling a watcher; it is active and its first check is due immediately.

        Args:
            watcher: Watcher to run every `watcher.interval`.

        Raises:
            ValueError: If a watcher with the same name was already added.
        """
        if watcher.name in self._watchers:
            msg = f"A watcher named {watcher.name!r} is already scheduled"
            raise ValueError(msg)
        self._watchers[watcher.name] = watcher
        self._states[watcher.name] = Active()
        self._due[watcher.name] = self._clock.now()

    def submit(self, command: Command) -> None:
        """Queue a command from any thread and wake `run_forever`, which applies it at once.

        Args:
            command: Command to apply.
        """
        self._commands.put(command)
        self._wake.set()

    def statuses(self) -> list[WatcherStatus]:
        """Return the state of every watcher, in the order they were added.

        The GUI calls it once, before the scheduler starts in its own thread,
        and then follows the events (see ADR-023).

        Returns:
            One status per watcher.
        """
        return [
            WatcherStatus(
                name=name,
                state=self._states[name].kind,
                interval=watcher.interval,
                last_check=self._last_check.get(name),
            )
            for name, watcher in self._watchers.items()
        ]

    def next_due(self) -> datetime | None:
        """Return when the next check is due.

        Returns:
            The earliest due time, or None if no watcher is checked.
        """
        return min(self._due.values(), default=None)

    def run_pending(self) -> int:
        """Apply the submitted commands, then check every watcher that is due now.

        Watchers are checked one after another. A failing check is logged and
        does not stop the others; the watcher's state decides when it is tried again.

        Returns:
            Number of watchers that were checked.
        """
        self._apply_commands()
        now = self._clock.now()
        due = [self._watchers[name] for name, due_at in self._due.items() if due_at <= now]
        for watcher in due:
            self._check(watcher)
        return len(due)

    def run_forever(self) -> None:
        """Check due watchers and wait for the next until `stop`, even one sent before the start."""
        while self._can_have_work() and not self._stop_requested:
            self.run_pending()
            self._clock.wait(self._seconds_until_next_due(), self._wake)
            self._wake.clear()
        self._stop_requested = False

    def stop(self) -> None:
        """Make `run_forever` return after the check that is running; safe from any thread."""
        self._stop_requested = True
        self._wake.set()

    def _apply_commands(self) -> None:
        """Apply every submitted command, oldest first."""
        while not self._commands.empty():
            self._apply(self._commands.get())

    def _apply(self, command: Command) -> None:
        """Apply one command; a command for an unknown watcher is logged and ignored.

        Args:
            command: Command taken from the queue.
        """
        match command:
            case ReloadConfig():
                self._reload()
            case _ if command.watcher_name not in self._watchers:
                _logger.warning("Ignoring %r: no watcher has that name", command)
            case Pause(watcher_name=name):
                self._set_state(self._watchers[name], Paused())
                self._schedule(name, None)
            case Resume(watcher_name=name):
                self._set_state(self._watchers[name], Active())
                self._schedule(name, timedelta(0))
            case CheckNow(watcher_name=name):
                self._schedule(name, timedelta(0))

    def _reload(self) -> None:
        """Replace the watchers with newly loaded ones; if loading fails, keep the old ones."""
        if self._load_watchers is None:
            _logger.warning("Ignoring ReloadConfig: the watchers were not loaded from a config")
            return
        try:
            watchers = self._load_watchers()
        except WatchtowerError as err:
            _logger.error("Config not reloaded, the old watchers keep running: %s", err)
        except Exception:
            _logger.exception("Unexpected error while reloading the config")
        else:
            self._replace_watchers(watchers)

    def _replace_watchers(self, watchers: Sequence[Watcher]) -> None:
        """Schedule new watchers instead of the old ones and publish ConfigReloaded.

        Args:
            watchers: Watchers to schedule from now on.
        """
        self._watchers.clear()
        self._states.clear()
        self._due.clear()
        self._last_check.clear()
        for watcher in watchers:
            self.add(watcher)
        if self._event_bus is not None:
            self._event_bus.publish(
                ConfigReloaded(statuses=tuple(self.statuses()), timestamp=self._clock.now())
            )

    def _check(self, watcher: Watcher) -> None:
        """Run one check, move the watcher to its next state and schedule it.

        Args:
            watcher: Watcher to check.
        """
        ok = self._run_check(watcher)
        state = self._states[watcher.name]
        new_state = state.after_success() if ok else state.after_failure()
        self._set_state(watcher, new_state)

        self._last_check[watcher.name] = self._clock.now()
        delay = new_state.delay(watcher.interval)
        self._schedule(watcher.name, delay)
        if isinstance(new_state, Backoff):
            _logger.info(
                "%r failed %d time(s) in a row; next check in %s",
                watcher.name,
                new_state.failures,
                delay,
            )

    def _run_check(self, watcher: Watcher) -> bool:
        """Run one check: a WatchtowerError is logged at DEBUG, any other exception as a bug.

        Args:
            watcher: Watcher to check.

        Returns:
            True if the check succeeded.
        """
        ok = False
        try:
            watcher.check_once()
            ok = True
        except WatchtowerError as err:
            _logger.debug("Watcher %r failed: %s", watcher.name, err)
        except Exception:
            _logger.exception("Unexpected error in watcher %r", watcher.name)
        return ok

    def _schedule(self, name: str, delay: timedelta | None) -> None:
        """Set when a watcher is checked next, counting from now.

        Args:
            name: Name of the watcher.
            delay: Time until its next check; None means it is not checked.
        """
        if delay is None:
            self._due.pop(name, None)
        else:
            self._due[name] = self._clock.now() + delay

    def _set_state(self, watcher: Watcher, new_state: State) -> None:
        """Give a watcher a new state and publish WatcherStateChanged if its kind changed.

        Args:
            watcher: Watcher whose state changes.
            new_state: Its new state.
        """
        old_state = self._states[watcher.name]
        self._states[watcher.name] = new_state
        if new_state.kind is not old_state.kind and watcher.event_bus is not None:
            watcher.event_bus.publish(
                WatcherStateChanged(
                    watcher_name=watcher.name,
                    old_state=old_state.kind,
                    new_state=new_state.kind,
                    timestamp=self._clock.now(),
                )
            )

    def _can_have_work(self) -> bool:
        """Return whether there is a watcher to check, now or after a reload.

        Returns:
            True if a watcher is scheduled or a ReloadConfig may bring some.
        """
        return bool(self._watchers) or self._load_watchers is not None

    def _seconds_until_next_due(self) -> float | None:
        """Return how long to wait before the earliest due check.

        Returns:
            Seconds until the next check, 0 if one is already due, or None if
            no watcher is checked (then only a command ends the wait).
        """
        next_due = self.next_due()
        until_due = None if next_due is None else next_due - self._clock.now()
        return None if until_due is None else max(until_due.total_seconds(), 0.0)
