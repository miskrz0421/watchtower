"""The tabs of the main window."""

from watchtower.gui.tabs._changes import ChangesTab, ChangesTableModel
from watchtower.gui.tabs._log import LogTab
from watchtower.gui.tabs._reports import ReportsTab
from watchtower.gui.tabs._watchers import WatchersTab, WatchersTableModel

__all__ = [
    "ChangesTab",
    "ChangesTableModel",
    "LogTab",
    "ReportsTab",
    "WatchersTab",
    "WatchersTableModel",
]
