"""Watchers tab: the state of every watcher, with Pause, Resume and Check now."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel
from PySide6.QtWidgets import QVBoxLayout, QWidget

from watchtower._events import CheckCompleted, WatcherStateChanged
from watchtower.core._scheduler import Scheduler
from watchtower.core._states import WatcherStatus
from watchtower.gui._bridge import EngineBridge


class WatchersTableModel(QAbstractTableModel):
    """One row per watcher: name, interval, state and last check."""

    def set_statuses(self, statuses: list[WatcherStatus]) -> None:
        """Replace all rows, e.g. with `Scheduler.statuses()` when the window opens.

        Args:
            statuses: One status per watcher.
        """
        raise NotImplementedError

    def update_state(self, changed: WatcherStateChanged) -> None:
        """Show a watcher's new state.

        Args:
            changed: Event published when the watcher changed state.
        """
        raise NotImplementedError

    def update_last_check(self, check: CheckCompleted) -> None:
        """Show when a watcher was last checked.

        Args:
            check: Event published at the end of the check.
        """
        raise NotImplementedError


class WatchersTab(QWidget):
    """Table of watchers; its buttons send commands with `Scheduler.submit`."""

    def __init__(
        self, bridge: EngineBridge, scheduler: Scheduler, parent: QWidget | None = None
    ) -> None:
        """Initialize WatchersTab.

        Args:
            bridge: Signals of the running engine.
            scheduler: Scheduler to read statuses from and send commands to.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        QVBoxLayout(self)
