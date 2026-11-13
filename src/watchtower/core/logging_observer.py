"""LoggingObserver writing bus events to the log."""

from __future__ import annotations

from watchtower.events import EventBus


class LoggingObserver:
    """Logs what every watcher does, using the standard `logging` module.

    Completed checks and detected changes are logged at INFO, failed fetches
    at WARNING.
    """

    def attach(self, event_bus: EventBus) -> None:
        """Start logging the events published on a bus.

        Args:
            event_bus: Bus to subscribe to.
        """
        raise NotImplementedError
