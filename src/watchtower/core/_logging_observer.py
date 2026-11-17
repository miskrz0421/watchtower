"""LoggingObserver writing bus events to the log."""

from __future__ import annotations

import logging

from watchtower._events import ChangeDetected, CheckCompleted, EventBus

_logger = logging.getLogger(__name__)


class LoggingObserver:
    """Logs what every watcher does, using the standard `logging` module.

    Successful checks and detected changes are logged at INFO, failed checks
    at WARNING. FetchFailed is not logged on its own: the CheckCompleted that
    follows it carries the same error.
    """

    def attach(self, event_bus: EventBus) -> None:
        """Start logging the events published on a bus.

        Args:
            event_bus: Bus to subscribe to.
        """
        event_bus.subscribe(CheckCompleted, self._log_check)
        event_bus.subscribe(ChangeDetected, self._log_change)

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
