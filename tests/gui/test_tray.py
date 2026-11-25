"""Tests for the TrayIcon."""

from __future__ import annotations

from datetime import timedelta

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSystemTrayIcon, QWidget
from pytestqt.qtbot import QtBot

from watchtower import ConfigReloaded, EventBus, WatcherState, WatcherStateChanged
from watchtower.core import ReloadConfig, Scheduler, Watcher, WatcherStatus
from watchtower.diffs import TextDiff
from watchtower.gui import EngineBridge, TrayIcon
from watchtower.sources import FakeSource

pytestmark = pytest.mark.gui


def _tray(qtbot: QtBot, scheduler: Scheduler) -> tuple[TrayIcon, EngineBridge, QWidget]:
    """Return a tray icon for the scheduler, with its bridge and a stand-in window."""
    window = QWidget()
    qtbot.addWidget(window)
    bridge = EngineBridge()
    return TrayIcon(bridge, scheduler, window), bridge, window


def _menu_action(tray: TrayIcon, text: str) -> None:
    """Click the tray menu entry with the given text."""
    menu = tray.contextMenu()
    assert menu is not None
    [action] = [action for action in menu.actions() if action.text() == text]
    action.trigger()


def _icon_colour(tray: TrayIcon) -> QColor:
    """Return the colour in the middle of the tray icon."""
    return tray.icon().pixmap(32, 32).toImage().pixelColor(16, 16)


def _state_changed(new_state: WatcherState) -> WatcherStateChanged:
    """Return the event of watcher 'hourly' moving from active to a new state."""
    return WatcherStateChanged(
        watcher_name="hourly", old_state=WatcherState.ACTIVE, new_state=new_state
    )


def test_icon_starts_green_with_the_states_in_the_tooltip(
    qtbot: QtBot, hourly_scheduler: Scheduler
) -> None:
    """Test that a new tray shows every watcher as active."""
    tray, _, _ = _tray(qtbot, hourly_scheduler)

    assert _icon_colour(tray) == QColor("#2e9e44")
    assert tray.toolTip() == "Watchtower: 1 active"


@pytest.mark.parametrize(
    ("new_state", "colour"),
    [
        (WatcherState.BACKOFF, "#e8a317"),
        (WatcherState.DISABLED, "#d64545"),
        (WatcherState.PAUSED, "#8a8a8a"),
    ],
)
def test_state_change_recolours_the_icon(
    qtbot: QtBot, hourly_scheduler: Scheduler, new_state: WatcherState, colour: str
) -> None:
    """Test that the bridge's state_changed signal updates the icon and the tooltip."""
    tray, bridge, _ = _tray(qtbot, hourly_scheduler)

    bridge.state_changed.emit(_state_changed(new_state))

    assert _icon_colour(tray) == QColor(colour)
    assert tray.toolTip() == f"Watchtower: 1 {new_state}"


def test_worst_state_wins(qtbot: QtBot, bus: EventBus, hourly_scheduler: Scheduler) -> None:
    """Test that one watcher in backoff makes the icon orange although another is active."""
    hourly_scheduler.add(
        Watcher(name="other", source=FakeSource(), differ=TextDiff(), event_bus=bus)
    )
    tray, bridge, _ = _tray(qtbot, hourly_scheduler)

    bridge.state_changed.emit(_state_changed(WatcherState.BACKOFF))

    assert _icon_colour(tray) == QColor("#e8a317")
    assert tray.toolTip() == "Watchtower: 1 active, 1 backoff"


def test_pause_all_and_resume_all_send_commands(qtbot: QtBot, hourly_scheduler: Scheduler) -> None:
    """Test that the menu's Pause all and Resume all reach every watcher through the queue."""
    tray, _, _ = _tray(qtbot, hourly_scheduler)

    _menu_action(tray, "Pause all")
    hourly_scheduler.run_pending()
    paused = [status.state for status in hourly_scheduler.statuses()]
    _menu_action(tray, "Resume all")
    hourly_scheduler.run_pending()
    resumed = [status.state for status in hourly_scheduler.statuses()]

    assert paused == [WatcherState.PAUSED]
    assert resumed == [WatcherState.ACTIVE]


def test_reload_config_sends_the_command(
    qtbot: QtBot, hourly_scheduler: Scheduler, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the menu's Reload config sends one command for the whole config."""
    submitted: list[object] = []
    monkeypatch.setattr(hourly_scheduler, "submit", submitted.append)
    tray, _, _ = _tray(qtbot, hourly_scheduler)

    _menu_action(tray, "Reload config")

    assert submitted == [ReloadConfig()]


def test_reload_replaces_the_states(qtbot: QtBot, hourly_scheduler: Scheduler) -> None:
    """Test that after a reload the icon shows the new watchers and forgets the old ones."""
    tray, bridge, _ = _tray(qtbot, hourly_scheduler)
    bridge.state_changed.emit(_state_changed(WatcherState.DISABLED))
    new_status = WatcherStatus("new", WatcherState.ACTIVE, timedelta(hours=1), None)

    bridge.config_reloaded.emit(ConfigReloaded(statuses=(new_status,)))

    assert _icon_colour(tray) == QColor("#2e9e44")
    assert tray.toolTip() == "Watchtower: 1 active"


def test_open_shows_the_window(qtbot: QtBot, hourly_scheduler: Scheduler) -> None:
    """Test that the menu's Open shows a hidden window."""
    tray, _, window = _tray(qtbot, hourly_scheduler)

    _menu_action(tray, "Open")

    assert window.isVisible()


def test_clicking_the_icon_shows_the_window(qtbot: QtBot, hourly_scheduler: Scheduler) -> None:
    """Test that a click on the icon itself opens the window, and other activations do not."""
    tray, _, window = _tray(qtbot, hourly_scheduler)

    tray.activated.emit(QSystemTrayIcon.ActivationReason.Context)
    shown_by_context = window.isVisible()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)

    assert not shown_by_context
    assert window.isVisible()


def test_tooltip_without_watchers(qtbot: QtBot) -> None:
    """Test that a config without watchers still gets a sensible tooltip."""
    tray, _, _ = _tray(qtbot, Scheduler())
    assert tray.toolTip() == "Watchtower: no watchers"
