"""Reports tab: charts of the history."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from watchtower.storage._history import HistoryStore


class ReportsTab(QWidget):
    """Charts of the history, with a watcher picker."""

    def __init__(self, history: HistoryStore | None, parent: QWidget | None = None) -> None:
        """Initialize ReportsTab.

        Args:
            history: History to draw; None when the config has no database.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        QVBoxLayout(self)
