"""Log tab: Watchtower's log lines while the app runs."""

from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from watchtower.gui._bridge import EngineBridge

_MAX_LINES = 1000


class LogTab(QWidget):
    """Read-only view of the last log lines, newest at the bottom."""

    def __init__(self, bridge: EngineBridge, parent: QWidget | None = None) -> None:
        """Initialize LogTab.

        Args:
            bridge: Bridge whose `line_logged` signal carries the lines.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self._lines = QPlainTextEdit(self)
        self._lines.setReadOnly(True)
        self._lines.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._lines.setMaximumBlockCount(_MAX_LINES)
        QVBoxLayout(self).addWidget(self._lines)
        # appendPlainText shows the line as it is, so `<` in a message is not read as HTML.
        bridge.line_logged.connect(self._lines.appendPlainText)
