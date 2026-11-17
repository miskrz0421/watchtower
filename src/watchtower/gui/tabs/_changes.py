"""Changes tab: every reported change, searchable, with the details of one."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel
from PySide6.QtWidgets import QVBoxLayout, QWidget

from watchtower._events import ChangeDetected
from watchtower.gui._bridge import EngineBridge
from watchtower.storage._history import ChangeRecord, HistoryStore


class ChangesTableModel(QAbstractTableModel):
    """One row per reported change, newest first."""

    def load(self, records: Iterable[ChangeRecord]) -> None:
        """Replace all rows with changes read from the history.

        Args:
            records: Saved changes, oldest first, as `HistoryStore.changes()` yields them.
        """
        raise NotImplementedError

    def add_event(self, detected: ChangeDetected) -> None:
        """Add a row for each change of a new event.

        Args:
            detected: Event published when a check found changes.
        """
        raise NotImplementedError


class ChangesTab(QWidget):
    """Search box, table of changes and the details of the selected one."""

    def __init__(
        self, bridge: EngineBridge, history: HistoryStore | None, parent: QWidget | None = None
    ) -> None:
        """Initialize ChangesTab.

        Args:
            bridge: Signals of the running engine.
            history: Saved changes to show first; None when the config has no database.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        QVBoxLayout(self)
