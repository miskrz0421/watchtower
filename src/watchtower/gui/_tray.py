"""TrayIcon showing the overall health of the watchers."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from watchtower._events import WatcherState, WatcherStateChanged
from watchtower.core._commands import Pause, Resume
from watchtower.core._scheduler import Scheduler
from watchtower.gui._bridge import EngineBridge
from watchtower.gui._colours import STATE_COLOURS

_ICON_SIZE = 64


class TrayIcon(QSystemTrayIcon):
    """Tray icon coloured by the worst watcher state, with Open, Pause all, Resume all and Quit."""

    def __init__(
        self,
        bridge: EngineBridge,
        scheduler: Scheduler,
        window: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Initialize TrayIcon.

        Args:
            bridge: Signals of the running engine.
            scheduler: Scheduler to read the states from and send commands to.
            window: Main window that Open shows.
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._scheduler = scheduler
        self._window = window
        self._states = {status.name: status.state for status in scheduler.statuses()}
        self._menu = self._build_menu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        bridge.state_changed.connect(self.update_state)
        self._show_health()

    def update_state(self, changed: WatcherStateChanged) -> None:
        """Show a watcher's new state in the icon and its tooltip.

        Args:
            changed: Event published when the watcher changed state.
        """
        self._states[changed.watcher_name] = changed.new_state
        self._show_health()

    def open_window(self) -> None:
        """Show the main window in front of the others."""
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def pause_all(self) -> None:
        """Ask the scheduler to pause every watcher."""
        for name in self._states:
            self._scheduler.submit(Pause(name))

    def resume_all(self) -> None:
        """Ask the scheduler to resume every watcher."""
        for name in self._states:
            self._scheduler.submit(Resume(name))

    def _build_menu(self) -> QMenu:
        """Create the right-click menu.

        Returns:
            The menu with Open, Pause all, Resume all and Quit.
        """
        menu = QMenu()
        for text, slot in [
            ("Open", self.open_window),
            ("Pause all", self.pause_all),
            ("Resume all", self.resume_all),
            ("Quit", QApplication.quit),
        ]:
            action = QAction(text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        return menu

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Open the window when the icon itself is clicked.

        Args:
            reason: How the icon was activated.
        """
        if reason is QSystemTrayIcon.ActivationReason.Trigger:
            self.open_window()

    def _show_health(self) -> None:
        """Colour the icon by the worst state and list the states in the tooltip."""
        self.setIcon(_dot_icon(_health_colour(set(self._states.values()))))
        counts = Counter(self._states.values())
        parts = [f"{counts[state]} {state}" for state in WatcherState if counts[state]]
        self.setToolTip("Watchtower: " + (", ".join(parts) or "no watchers"))


def _health_colour(states: set[WatcherState]) -> QColor:
    """Return the colour of the worst state; paused watchers count only when all are paused.

    Args:
        states: The states of all watchers.

    Returns:
        The colour for the tray icon.
    """
    if WatcherState.DISABLED in states:
        worst = WatcherState.DISABLED
    elif WatcherState.BACKOFF in states:
        worst = WatcherState.BACKOFF
    elif states == {WatcherState.PAUSED}:
        worst = WatcherState.PAUSED
    else:
        worst = WatcherState.ACTIVE
    return STATE_COLOURS[worst]


def _dot_icon(colour: QColor) -> QIcon:
    """Draw a filled circle in a colour.

    Args:
        colour: Fill colour.

    Returns:
        The icon.
    """
    pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawEllipse(4, 4, _ICON_SIZE - 8, _ICON_SIZE - 8)
    painter.end()
    return QIcon(pixmap)
