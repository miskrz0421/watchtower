"""HistoryRecorder saving bus events to the HistoryStore (Observer pattern)."""

from __future__ import annotations

from watchtower.events import EventBus
from watchtower.storage.history import HistoryStore


class HistoryRecorder:
    """Writes every finished check and every reported change to the history.

    Watchers know nothing about the history: the recorder listens on the
    event bus (see ADR-006).
    """

    def __init__(self, store: HistoryStore) -> None:
        """Initialize HistoryRecorder.

        Args:
            store: Store the events are saved to.
        """
        raise NotImplementedError

    def attach(self, event_bus: EventBus) -> None:
        """Start recording the CheckCompleted and ChangeDetected events of a bus.

        Args:
            event_bus: Bus to subscribe to.
        """
        raise NotImplementedError
