"""Tests for the LogTab."""

from __future__ import annotations

import threading

import pytest
from PySide6.QtWidgets import QPlainTextEdit
from pytestqt.qtbot import QtBot

from watchtower.gui import EngineBridge
from watchtower.gui.tabs import LogTab

pytestmark = pytest.mark.gui


def _log_tab(qtbot: QtBot) -> tuple[LogTab, EngineBridge, QPlainTextEdit]:
    """Return a log tab with its bridge and its text view."""
    bridge = EngineBridge()
    tab = LogTab(bridge)
    qtbot.addWidget(tab)
    view = tab.findChild(QPlainTextEdit)
    assert view is not None
    return tab, bridge, view


def test_lines_are_appended_as_plain_text(qtbot: QtBot) -> None:
    """Test that lines appear in order, without reading HTML in them, and cannot be edited."""
    _tab, bridge, view = _log_tab(qtbot)

    bridge.line_logged.emit("first")
    bridge.line_logged.emit("<b>second</b>")

    assert view.toPlainText() == "first\n<b>second</b>"
    assert view.isReadOnly()


def test_only_the_last_lines_are_kept(qtbot: QtBot) -> None:
    """Test that a long run does not fill the memory."""
    _tab, bridge, view = _log_tab(qtbot)

    for number in range(1001):
        bridge.line_logged.emit(f"line {number}")

    assert view.blockCount() == 1000
    assert view.toPlainText().startswith("line 1\n")


def test_line_from_another_thread_is_shown(qtbot: QtBot) -> None:
    """Test that a line logged by the engine thread reaches the view."""
    _tab, bridge, view = _log_tab(qtbot)

    engine = threading.Thread(target=bridge.line_logged.emit, args=("from the engine",))
    engine.start()
    engine.join()

    qtbot.waitUntil(lambda: view.toPlainText() == "from the engine")
