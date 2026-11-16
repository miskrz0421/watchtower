"""HistoryRecorder saving bus events to the HistoryStore (Observer pattern)."""

from __future__ import annotations

from watchtower._events import ChangeDetected, CheckCompleted, EventBus
from watchtower.storage._history import HistoryStore


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
        self._store = store

    def attach(self, event_bus: EventBus) -> None:
        """Start recording the CheckCompleted and ChangeDetected events of a bus.

        Args:
            event_bus: Bus to subscribe to.
        """
        event_bus.subscribe(CheckCompleted, self._on_check_completed)
        event_bus.subscribe(ChangeDetected, self._on_change_detected)

    def _on_check_completed(self, event: CheckCompleted) -> None:
        """Record a completed check event in the store."""
        self._store.record_check(event)

    def _on_change_detected(self, detected: ChangeDetected) -> None:
        """Record detected changes in the store."""
        self._store.record_changes(detected.event)
