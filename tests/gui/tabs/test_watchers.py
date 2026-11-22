"""Tests for WatchersTableModel and WatchersTab."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QTableView
from pytestqt.qtbot import QtBot

from watchtower import CheckCompleted, WatcherState, WatcherStateChanged
from watchtower.core import CheckNow, Pause, Resume, Scheduler, WatcherStatus
from watchtower.gui import EngineBridge
from watchtower.gui.tabs import WatchersTab, WatchersTableModel
from watchtower.gui.tabs._watchers import _format_interval

pytestmark = pytest.mark.gui


def _statuses() -> list[WatcherStatus]:
    """Return two statuses: one checked and active, one paused and never checked."""
    checked_at = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)
    return [
        WatcherStatus("flats", WatcherState.ACTIVE, timedelta(hours=1), checked_at),
        WatcherStatus("news", WatcherState.PAUSED, timedelta(minutes=15), None),
    ]


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        (timedelta(0), "0s"),
        (timedelta(seconds=45), "45s"),
        (timedelta(minutes=15), "15m"),
        (timedelta(hours=1, minutes=30), "1h 30m"),
        (timedelta(hours=2, seconds=3), "2h 3s"),
        (timedelta(days=1, hours=1, minutes=30, seconds=5), "1d 1h 30m 5s"),
    ],
)
def test_format_interval(interval: timedelta, expected: str) -> None:
    """Test that intervals use compact units and drop zero components."""
    assert _format_interval(interval) == expected


def test_model_empty_on_creation() -> None:
    """Test that a new WatchersTableModel is empty with valid column headers."""
    model = WatchersTableModel()

    assert model.rowCount() == 0
    assert model.columnCount() == 4
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Name"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Interval"
    assert model.headerData(2, Qt.Orientation.Horizontal) == "State"
    assert model.headerData(3, Qt.Orientation.Horizontal) == "Last checked"
    assert model.headerData(4, Qt.Orientation.Horizontal) is None
    assert model.data(model.index(0, 0)) is None


def test_model_displays_statuses() -> None:
    """Test that each status is shown in its four columns."""
    model = WatchersTableModel()
    model.set_statuses(_statuses())
    checked_at = _statuses()[0].last_check
    assert checked_at is not None
    expected_time = checked_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    assert model.rowCount() == 2
    assert model.data(model.index(0, 0)) == "flats"
    assert model.data(model.index(0, 1)) == "1h"
    assert model.data(model.index(0, 2)) == "● active"
    assert model.data(model.index(0, 3)) == expected_time
    assert model.data(model.index(1, 0)) == "news"
    assert model.data(model.index(1, 1)) == "15m"
    assert model.data(model.index(1, 2)) == "○ paused"
    assert model.data(model.index(1, 3)) == "never"


def test_model_colours_the_state_badge() -> None:
    """Test that the state cell uses the same colours as the tray icon."""
    model = WatchersTableModel()
    model.set_statuses(_statuses())

    assert model.data(model.index(0, 2), Qt.ItemDataRole.ForegroundRole) == QColor("#2e9e44")
    assert model.data(model.index(1, 2), Qt.ItemDataRole.ForegroundRole) == QColor("#8a8a8a")
    assert model.data(model.index(0, 0), Qt.ItemDataRole.ForegroundRole) is None


def test_model_updates_state_and_last_check() -> None:
    """Test that state and check events change only the corresponding cell."""
    model = WatchersTableModel()
    model.set_statuses(_statuses())
    now = datetime(2026, 11, 22, 11, 0, tzinfo=UTC)

    model.update_state(
        WatcherStateChanged(
            watcher_name="flats",
            old_state=WatcherState.ACTIVE,
            new_state=WatcherState.BACKOFF,
            timestamp=now,
        )
    )
    assert model.data(model.index(0, 2)) == "● backoff"
    assert model.data(model.index(0, 2), Qt.ItemDataRole.ForegroundRole) == QColor("#e8a317")

    model.update_last_check(
        CheckCompleted(watcher_name="flats", duration_seconds=0.5, ok=False, timestamp=now)
    )
    assert model.data(model.index(0, 3)) == now.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def test_state_change_updates_one_row(qtbot: QtBot) -> None:
    """Test that a state change emits dataChanged for only that watcher's state cell."""
    model = WatchersTableModel()
    model.set_statuses(_statuses())
    now = datetime(2026, 11, 22, 11, 0, tzinfo=UTC)

    with qtbot.waitSignal(model.dataChanged) as blocker:
        model.update_state(
            WatcherStateChanged(
                watcher_name="news",
                old_state=WatcherState.PAUSED,
                new_state=WatcherState.ACTIVE,
                timestamp=now,
            )
        )

    top_left, bottom_right, roles = blocker.args
    changed_cell = model.index(1, 2)
    assert top_left == changed_cell
    assert bottom_right == changed_cell
    assert set(roles) == {int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.ForegroundRole)}
    assert model.data(model.index(0, 2)) == "● active"
    assert model.data(model.index(1, 2)) == "● active"


def test_model_ignores_events_for_unknown_watchers() -> None:
    """Test that an event for a watcher that is no longer shown does not add a row."""
    model = WatchersTableModel()
    model.set_statuses(_statuses())
    now = datetime(2026, 11, 22, 11, 0, tzinfo=UTC)

    model.update_state(
        WatcherStateChanged(
            watcher_name="gone",
            old_state=WatcherState.ACTIVE,
            new_state=WatcherState.PAUSED,
            timestamp=now,
        )
    )
    model.update_last_check(
        CheckCompleted(watcher_name="gone", duration_seconds=0.5, ok=True, timestamp=now)
    )

    assert model.rowCount() == 2
    assert model.data(model.index(0, 2)) == "● active"


def test_tab_buttons_submit_commands_for_the_selected_watcher(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that Pause, Resume and Check now submit a command for the selected row."""
    scheduler = Scheduler()
    submitted: list[object] = []
    monkeypatch.setattr(scheduler, "submit", submitted.append)
    monkeypatch.setattr(scheduler, "statuses", _statuses)
    tab = WatchersTab(EngineBridge(), scheduler)
    qtbot.addWidget(tab)
    table = tab.findChild(QTableView)
    assert table is not None
    buttons = {button.text(): button for button in tab.findChildren(QPushButton)}
    assert set(buttons) == {"Pause", "Resume", "Check now"}

    table.selectRow(0)
    buttons["Pause"].click()
    buttons["Resume"].click()
    buttons["Check now"].click()

    assert submitted == [Pause("flats"), Resume("flats"), CheckNow("flats")]


def test_tab_ignores_buttons_when_no_watcher_is_selected(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that clicking a button with no selection submits nothing."""
    scheduler = Scheduler()
    submitted: list[object] = []
    monkeypatch.setattr(scheduler, "submit", submitted.append)
    monkeypatch.setattr(scheduler, "statuses", _statuses)
    tab = WatchersTab(EngineBridge(), scheduler)
    qtbot.addWidget(tab)
    buttons = {button.text(): button for button in tab.findChildren(QPushButton)}

    buttons["Pause"].click()

    assert submitted == []


def test_tab_updates_from_bridge_signals(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the table follows the state and check events from the engine."""
    bridge = EngineBridge()
    scheduler = Scheduler()
    monkeypatch.setattr(scheduler, "statuses", _statuses)
    tab = WatchersTab(bridge, scheduler)
    qtbot.addWidget(tab)
    table = tab.findChild(QTableView)
    assert table is not None
    model = table.model()
    assert model is not None
    now = datetime(2026, 11, 22, 11, 0, tzinfo=UTC)

    bridge.state_changed.emit(
        WatcherStateChanged(
            watcher_name="news",
            old_state=WatcherState.PAUSED,
            new_state=WatcherState.ACTIVE,
            timestamp=now,
        )
    )
    bridge.check_completed.emit(
        CheckCompleted(watcher_name="news", duration_seconds=0.5, ok=True, timestamp=now)
    )

    assert model.data(model.index(1, 2)) == "● active"
    assert model.data(model.index(1, 3)) == now.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def test_tab_reads_statuses_from_the_scheduler(qtbot: QtBot, hourly_scheduler: Scheduler) -> None:
    """Test that the tab gets its rows from `Scheduler.statuses()`."""
    tab = WatchersTab(EngineBridge(), hourly_scheduler)
    qtbot.addWidget(tab)
    table = tab.findChild(QTableView)
    assert table is not None

    assert table.model().rowCount() == 1
    assert table.model().data(table.model().index(0, 0)) == "hourly"
