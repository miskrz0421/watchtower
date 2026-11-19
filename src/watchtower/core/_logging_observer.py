"""LoggingObserver writing bus events to the log."""

from __future__ import annotations

import logging

from watchtower._events import (
    ChangeDetected,
    CheckCompleted,
    EventBus,
    WatcherState,
    WatcherStateChanged,
)

_logger = logging.getLogger(__name__)


class LoggingObserver:
    """Logs checks, changes and state changes; failures at WARNING (ADR-020, ADR-023)."""

    def attach(self, event_bus: EventBus) -> None:
        """Start logging the events published on a bus.

        Args:
            event_bus: Bus to subscribe to.
        """
        event_bus.subscribe(CheckCompleted, self._log_check)
        event_bus.subscribe(ChangeDetected, self._log_change)
        event_bus.subscribe(WatcherStateChanged, self._log_state)

    def _log_check(self, check: CheckCompleted) -> None:
        """Log the outcome of a finished check.

        Args:
            check: Event published at the end of the check.
        """
        level = logging.INFO if check.ok else logging.WARNING
        outcome = "ok" if check.ok else f"failed: {check.error}"
        _logger.log(
            level,
            "Checked %r in %.2f s: %s",
            check.watcher_name,
            check.duration_seconds,
            outcome,
        )

    def _log_change(self, detected: ChangeDetected) -> None:
        """Log a summary of the changes a check reported.

        Args:
            detected: Event published when the check found changes.
        """
        _logger.info("%r: %s", detected.watcher_name, detected.event.summary)

    def _log_state(self, changed: WatcherStateChanged) -> None:
        """Log a watcher's move to another state.

        Args:
            changed: Event published when the watcher changed state.
        """
        failing = changed.new_state in (WatcherState.BACKOFF, WatcherState.DISABLED)
        level = logging.WARNING if failing else logging.INFO
        _logger.log(
            level,
            "%r is now %s (was %s)",
            changed.watcher_name,
            changed.new_state,
            changed.old_state,
        )
