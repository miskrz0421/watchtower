"""Shared colours for GUI widgets."""

from __future__ import annotations

from PySide6.QtGui import QColor

from watchtower._events import WatcherState

STATE_COLOURS: dict[WatcherState, QColor] = {
    WatcherState.ACTIVE: QColor("#2e9e44"),
    WatcherState.BACKOFF: QColor("#e8a317"),
    WatcherState.PAUSED: QColor("#8a8a8a"),
    WatcherState.DISABLED: QColor("#d64545"),
}
