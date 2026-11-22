"""Watchers tab: the state of every watcher, with Pause, Resume and Check now."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import NamedTuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTableView, QVBoxLayout, QWidget

from watchtower._events import CheckCompleted, WatcherState, WatcherStateChanged
from watchtower.core._commands import CheckNow, Pause, Resume
from watchtower.core._scheduler import Scheduler
from watchtower.core._states import WatcherStatus
from watchtower.gui._bridge import EngineBridge
from watchtower.gui._colours import STATE_COLOURS
from watchtower.gui._format import format_time

_COLUMNS: tuple[str, ...] = ("Name", "Interval", "State", "Last checked")
_ROOT_INDEX = QModelIndex()
_DISPLAY_ROLE = int(Qt.ItemDataRole.DisplayRole)
_FOREGROUND_ROLE = int(Qt.ItemDataRole.ForegroundRole)
_STATE_COLUMN = 2
_LAST_CHECK_COLUMN = 3

# A hollow dot marks a watcher that is not checked at all: Paused and Disabled
# both have no next check (ADR-023).
_DOTS: dict[WatcherState, str] = {
    WatcherState.ACTIVE: "●",
    WatcherState.BACKOFF: "●",
    WatcherState.PAUSED: "○",
    WatcherState.DISABLED: "○",
}


def _format_interval(interval: timedelta) -> str:
    """Return an interval like `1h 30m`, leaving out units that are zero.

    Args:
        interval: Time between checks of a watcher.

    Returns:
        Interval written with d, h, m and s, dropping units that are zero.
    """
    seconds = int(interval.total_seconds())
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    parts = [
        f"{value}{unit}"
        for value, unit in ((days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s"))
        if value
    ]
    return " ".join(parts) or "0s"


def _state_badge(state: WatcherState) -> str:
    """Return the state's dot and name, e.g. `● active`.

    Args:
        state: Runtime state of a watcher.

    Returns:
        Text of the state badge.
    """
    return f"{_DOTS[state]} {state.value}"


class _WatcherRow(NamedTuple):
    """Rendered table row for a single watcher status."""

    name: str
    interval: str
    state: str
    last_check: str


def _format_row(status: WatcherStatus) -> _WatcherRow:
    """Format a watcher's status into the four displayed columns.

    Args:
        status: Status to format.

    Returns:
        Rendered watcher row for display.
    """
    last_check = "never" if status.last_check is None else format_time(status.last_check)
    return _WatcherRow(
        name=status.name,
        interval=_format_interval(status.interval),
        state=_state_badge(status.state),
        last_check=last_check,
    )


class WatchersTableModel(QAbstractTableModel):
    """One row per watcher: name, interval, state and last check."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize WatchersTableModel.

        Args:
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._rows: list[WatcherStatus] = []
        self._row_of: dict[str, int] = {}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        """Return the number of rows in the model.

        Args:
            parent: Parent model index.

        Returns:
            Number of watchers.
        """
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        """Return the number of columns in the model.

        Args:
            parent: Parent model index.

        Returns:
            Number of columns.
        """
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = _DISPLAY_ROLE,
    ) -> str | None:
        """Return header data for rows and columns.

        Args:
            section: Column or row section index.
            orientation: Horizontal or vertical orientation.
            role: Display role.

        Returns:
            Column title or None.
        """
        if (
            orientation == Qt.Orientation.Horizontal
            and role == _DISPLAY_ROLE
            and 0 <= section < len(_COLUMNS)
        ):
            return _COLUMNS[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = _DISPLAY_ROLE,
    ) -> str | QColor | None:
        """Return the text or the badge colour of one cell.

        Args:
            index: Model index requesting data.
            role: Data role being queried.

        Returns:
            Cell text for DisplayRole, badge colour for ForegroundRole in the
            State column, or None for any other index or role.
        """
        if not index.isValid():
            return None
        status = self._rows[index.row()]
        if role == _DISPLAY_ROLE:
            return _format_row(status)[index.column()]
        if role == _FOREGROUND_ROLE and index.column() == _STATE_COLUMN:
            return STATE_COLOURS[status.state]
        return None

    def status_at(self, row: int) -> WatcherStatus:
        """Return the status shown at a row.

        Args:
            row: Zero-based row index.

        Returns:
            The watcher's status.
        """
        return self._rows[row]

    def set_statuses(self, statuses: list[WatcherStatus]) -> None:
        """Replace all rows, e.g. with the statuses read when the window opens.

        Args:
            statuses: One status per watcher.
        """
        self.beginResetModel()
        self._rows = list(statuses)
        self._row_of = {status.name: row for row, status in enumerate(self._rows)}
        self.endResetModel()

    def update_state(self, changed: WatcherStateChanged) -> None:
        """Show a watcher's new state.

        Args:
            changed: Event published when the watcher changed state.
        """
        row = self._row_of.get(changed.watcher_name)
        if row is None:
            return
        self._rows[row] = replace(self._rows[row], state=changed.new_state)
        self._emit_data_changed(row, _STATE_COLUMN, [_DISPLAY_ROLE, _FOREGROUND_ROLE])

    def update_last_check(self, check: CheckCompleted) -> None:
        """Show when a watcher was last checked.

        Args:
            check: Event published at the end of the check.
        """
        row = self._row_of.get(check.watcher_name)
        if row is None:
            return
        self._rows[row] = replace(self._rows[row], last_check=check.timestamp)
        self._emit_data_changed(row, _LAST_CHECK_COLUMN, [_DISPLAY_ROLE])

    def _emit_data_changed(self, row: int, column: int, roles: list[int]) -> None:
        """Tell attached views that one cell of a watcher changed.

        Args:
            row: Index of the watcher's row.
            column: Index of the changed column.
            roles: Roles whose values changed.
        """
        cell = self.index(row, column)
        self.dataChanged.emit(cell, cell, roles)


class WatchersTab(QWidget):
    """Table of watchers; its buttons send commands with `Scheduler.submit`."""

    def __init__(
        self, bridge: EngineBridge, scheduler: Scheduler, parent: QWidget | None = None
    ) -> None:
        """Initialize WatchersTab.

        Args:
            bridge: Signals of the running engine.
            scheduler: Scheduler to read statuses from and send commands to.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self._scheduler = scheduler
        layout = QVBoxLayout(self)

        self._model = WatchersTableModel(self)
        self._model.set_statuses(scheduler.statuses())

        self._table = QTableView(self)
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        layout.addWidget(self._table)

        buttons = QHBoxLayout()
        for text, slot in [
            ("Pause", self.pause_selected),
            ("Resume", self.resume_selected),
            ("Check now", self.check_now_selected),
        ]:
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        bridge.state_changed.connect(self._model.update_state)
        bridge.check_completed.connect(self._model.update_last_check)

    def pause_selected(self) -> None:
        """Ask the scheduler to pause the selected watcher."""
        name = self._selected_name()
        if name is not None:
            self._scheduler.submit(Pause(name))

    def resume_selected(self) -> None:
        """Ask the scheduler to resume the selected watcher."""
        name = self._selected_name()
        if name is not None:
            self._scheduler.submit(Resume(name))

    def check_now_selected(self) -> None:
        """Ask the scheduler to check the selected watcher at once."""
        name = self._selected_name()
        if name is not None:
            self._scheduler.submit(CheckNow(name))

    def _selected_name(self) -> str | None:
        """Return the name of the selected watcher, if one is selected.

        Returns:
            The watcher's name, or None when no row is selected.
        """
        rows = self._table.selectionModel().selectedRows()
        return self._model.status_at(rows[0].row()).name if rows else None
