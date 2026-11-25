"""MainWindow holding one tab per part of the app."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from watchtower.core._scheduler import Scheduler
from watchtower.gui._bridge import EngineBridge
from watchtower.gui.tabs._changes import ChangesTab
from watchtower.gui.tabs._log import LogTab
from watchtower.gui.tabs._reports import ReportsTab
from watchtower.gui.tabs._watchers import WatchersTab
from watchtower.storage._history import HistoryStore


class MainWindow(QMainWindow):
    """The app's window: Watchers, Changes, Reports and Log tabs."""

    def __init__(
        self,
        bridge: EngineBridge,
        scheduler: Scheduler,
        history: HistoryStore | None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize MainWindow.

        Args:
            bridge: Signals of the running engine.
            scheduler: Scheduler the Watchers tab reads and sends commands to.
            history: Saved changes and checks; None when the config has no database.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Watchtower")
        tabs = QTabWidget()
        tabs.addTab(WatchersTab(bridge, scheduler), "Watchers")
        tabs.addTab(ChangesTab(bridge, history), "Changes")
        tabs.addTab(ReportsTab(history), "Reports")
        tabs.addTab(LogTab(bridge), "Log")
        self.setCentralWidget(tabs)
