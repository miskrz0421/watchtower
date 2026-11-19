"""Desktop app: a tray icon and a window on top of the engine.

Needs the `gui` extra (PySide6); the core never imports this package (see
ADR-003 and ADR-024).
"""

from watchtower.gui._app import run_gui
from watchtower.gui._bridge import EngineBridge
from watchtower.gui._engine import EngineThread
from watchtower.gui._main_window import MainWindow
from watchtower.gui._tray import TrayIcon

__all__ = ["EngineBridge", "EngineThread", "MainWindow", "TrayIcon", "run_gui"]
