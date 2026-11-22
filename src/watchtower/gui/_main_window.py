"""MainWindow holding one tab per part of the app."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from watchtower.core._scheduler import Scheduler
from watchtower.core._states import WatcherStatus
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
        statuses: list[WatcherStatus] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize MainWindow.

        Args:
            bridge: Signals of the running engine.
            scheduler: Scheduler the Watchers tab sends commands to.
            history: Saved changes and checks; None when the config has no database.
            statuses: Statuses read before the engine started; None when the
                window is built on its own, outside `run_gui`.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Watchtower")
        tabs = QTabWidget()
        tabs.addTab(WatchersTab(bridge, scheduler, statuses), "Watchers")
        tabs.addTab(ChangesTab(bridge, history), "Changes")
        tabs.addTab(ReportsTab(history), "Reports")
        tabs.addTab(LogTab(), "Log")
        self.setCentralWidget(tabs)
