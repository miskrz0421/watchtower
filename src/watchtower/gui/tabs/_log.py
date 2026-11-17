"""Log tab: Watchtower's log lines while the app runs."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget


class LogTab(QWidget):
    """Read-only view of the log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize LogTab.

        Args:
            parent: Qt parent widget.
        """
        super().__init__(parent)
        QVBoxLayout(self)
