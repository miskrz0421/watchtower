"""EngineBridge turning bus events into Qt signals (Observer pattern)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from watchtower._events import (
    ChangeDetected,
    CheckCompleted,
    EventBus,
    FetchFailed,
    WatcherStateChanged,
)


class EngineBridge(QObject):
    """Re-emits the engine's bus events as Qt signals (see ADR-024).

    The bridge is created in the GUI thread and the engine publishes from its
    own thread. Qt then queues each signal to the thread of the QObject whose
    method is connected, so tabs connect their own methods, never lambdas.
    """

    check_completed = Signal(CheckCompleted)
    change_detected = Signal(ChangeDetected)
    fetch_failed = Signal(FetchFailed)
    state_changed = Signal(WatcherStateChanged)
    notification_requested = Signal(str, str)

    def attach(self, event_bus: EventBus) -> None:
        """Start re-emitting the events published on a bus.

        Args:
            event_bus: Bus the watchers and the scheduler publish on.
        """
        event_bus.subscribe(CheckCompleted, self.check_completed.emit)
        event_bus.subscribe(ChangeDetected, self.change_detected.emit)
        event_bus.subscribe(FetchFailed, self.fetch_failed.emit)
        event_bus.subscribe(WatcherStateChanged, self.state_changed.emit)
