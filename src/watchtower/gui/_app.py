"""Start of the desktop app."""

from __future__ import annotations

import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from watchtower._events import EventBus
from watchtower.core._scheduler import Scheduler
from watchtower.gui._bridge import EngineBridge
from watchtower.gui._engine import EngineThread
from watchtower.gui._log_handler import log_sent_to
from watchtower.gui._main_window import MainWindow
from watchtower.gui._tray import TrayIcon
from watchtower.storage._history import HistoryStore

_PYTHON_WAKE_UP_MS = 200


def run_gui(scheduler: Scheduler, event_bus: EventBus, history: HistoryStore | None) -> int:
    """Show the window and tray icon and run the scheduler in an EngineThread until Quit or Ctrl+C.

    Args:
        scheduler: Scheduler with every watcher added, not running yet.
        event_bus: Bus the watchers and the scheduler publish on.
        history: Saved changes and checks; None when the config has no database.

    Returns:
        The exit code of the Qt event loop.
    """
    app = _application()
    bridge = EngineBridge()
    bridge.attach(event_bus)
    window = MainWindow(bridge, scheduler, history)
    tray = TrayIcon(bridge, scheduler, window)
    engine = EngineThread(scheduler)
    # With a tray, closing the window only hides it; Quit in the tray menu ends the app.
    app.setQuitOnLastWindowClosed(not QSystemTrayIcon.isSystemTrayAvailable())

    window.show()
    tray.show()
    with log_sent_to(bridge):
        engine.start()
        with _ctrl_c_quits(app):
            exit_code = app.exec()
        engine.stop()
    return exit_code


def _application() -> QApplication:
    """Return the running QApplication, creating it if there is none yet.

    Returns:
        The application object.
    """
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication(sys.argv)


@contextmanager
def _ctrl_c_quits(app: QApplication) -> Iterator[None]:
    """Make Ctrl+C in the terminal quit the app while the block runs, as closing the window does.

    Args:
        app: Application to quit.

    Yields:
        Nothing; the previous Ctrl+C handler is back after the block.
    """
    # Qt's event loop runs Python signal handlers only when Python code runs, so a timer calls
    # an empty Python function regularly.
    wake_python = QTimer()
    wake_python.timeout.connect(_do_nothing)
    wake_python.start(_PYTHON_WAKE_UP_MS)
    previous = signal.signal(signal.SIGINT, lambda _signum, _frame: app.quit())
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
        wake_python.stop()


def _do_nothing() -> None:
    """Give Python a moment to run pending signal handlers."""
