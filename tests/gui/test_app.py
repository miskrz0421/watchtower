"""Tests for run_gui."""

from __future__ import annotations

import signal

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from watchtower import CheckCompleted, EventBus
from watchtower.core import Scheduler
from watchtower.gui import MainWindow, run_gui

pytestmark = pytest.mark.gui


def _open_main_window() -> MainWindow:
    """Return the MainWindow that run_gui showed."""
    windows = [
        widget
        for widget in QApplication.topLevelWidgets()
        if isinstance(widget, MainWindow) and widget.isVisible()
    ]
    assert len(windows) == 1
    return windows[0]


def test_app_checks_in_the_background_until_the_window_is_closed(
    qtbot: QtBot, bus: EventBus, hourly_scheduler: Scheduler
) -> None:
    """Test that run_gui shows the window, runs the engine and returns once the window closes."""
    checks: list[CheckCompleted] = []
    bus.subscribe(CheckCompleted, checks.append)

    def close_after_the_first_check() -> None:
        """Wait for the engine's first check, then close the window like the user would."""
        qtbot.waitUntil(lambda: len(checks) == 1)
        _open_main_window().close()

    QTimer.singleShot(0, close_after_the_first_check)
    QTimer.singleShot(10_000, QApplication.quit)  # never hang the test run

    assert run_gui(hourly_scheduler, bus, history=None) == 0
    assert len(checks) == 1


def test_ctrl_c_quits_the_app(qtbot: QtBot, bus: EventBus, hourly_scheduler: Scheduler) -> None:
    """Test that Ctrl+C in the terminal ends run_gui and leaves the old handler in place."""
    checks: list[CheckCompleted] = []
    bus.subscribe(CheckCompleted, checks.append)
    handler_before = signal.getsignal(signal.SIGINT)

    def press_ctrl_c_after_the_first_check() -> None:
        """Wait for the engine's first check, then send SIGINT like Ctrl+C does."""
        qtbot.waitUntil(lambda: len(checks) == 1)
        signal.raise_signal(signal.SIGINT)

    QTimer.singleShot(0, press_ctrl_c_after_the_first_check)
    QTimer.singleShot(10_000, QApplication.quit)  # never hang the test run

    assert run_gui(hourly_scheduler, bus, history=None) == 0
    assert signal.getsignal(signal.SIGINT) is handler_before
