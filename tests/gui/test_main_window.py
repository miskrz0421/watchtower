"""Tests for the MainWindow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QTabWidget
from pytestqt.qtbot import QtBot

from watchtower.core import Scheduler
from watchtower.gui import EngineBridge, MainWindow
from watchtower.storage import HistoryStore

pytestmark = pytest.mark.gui


def test_window_opens_with_a_tab_per_part(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that the window shows the Watchers, Changes, Reports and Log tabs."""
    window = MainWindow(EngineBridge(), Scheduler(), HistoryStore(tmp_path / "watchtower.db"))
    qtbot.addWidget(window)

    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Watchers",
        "Changes",
        "Reports",
        "Log",
    ]


def test_window_opens_without_a_database(qtbot: QtBot) -> None:
    """Test that a config without a database still gets a window."""
    window = MainWindow(EngineBridge(), Scheduler(), history=None)
    qtbot.addWidget(window)

    assert window.windowTitle() == "Watchtower"
