"""Watchers tab: the state of every watcher, with Pause, Resume and Check now."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTableView, QVBoxLayout, QWidget

from watchtower._events import CheckCompleted, WatcherState, WatcherStateChanged
from watchtower.core._commands import CheckNow, Pause, Resume
from watchtower.core._scheduler import Scheduler
from watchtower.core._states import WatcherStatus
from watchtower.gui._bridge import EngineBridge
from watchtower.gui._format import format_time
from watchtower.gui._statuses import initial_statuses

_COLUMNS: tuple[str, ...] = ("Name", "Interval", "State", "Last Checked")
_ROOT_INDEX = QModelIndex()
_DISPLAY_ROLE = int(Qt.ItemDataRole.DisplayRole)
_FOREGROUND_ROLE = int(Qt.ItemDataRole.ForegroundRole)

# The same colors as the tray (ADR-024). A hollow dot marks a watcher that is
# not checked at all: Paused and Disabled both have no next check (ADR-023).
_STATE_STYLES: dict[WatcherState, tuple[str, QColor]] = {
    WatcherState.ACTIVE: ("●", QColor("#2e9e44")),
    WatcherState.BACKOFF: ("●", QColor("#e8a317")),
    WatcherState.PAUSED: ("○", QColor("#8a8a8a")),
    WatcherState.DISABLED: ("○", QColor("#d64545")),
}


def _format_interval(interval: timedelta) -> str:
    """Return an interval in the compact form used in the config, e.g. `1h 30m`.

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
    dot, _colour = _STATE_STYLES[state]
    return f"{dot} {state.value}"


def _state_colour(state: WatcherState) -> QColor:
    """Return the colour of a state's badge.

    Args:
        state: Runtime state of a watcher.

    Returns:
        Colour used for the badge text.
    """
    return _STATE_STYLES[state][1]


class WatchersTableModel(QAbstractTableModel):
    """One row per watcher: name, interval, state and last check."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize WatchersTableModel.

        Args:
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._statuses: dict[str, WatcherStatus] = {}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        """Return the number of rows in the model.

        Args:
            parent: Parent model index.

        Returns:
            Number of watchers.
        """
        return 0 if parent.isValid() else len(self._statuses)

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
        if not index.isValid() or not 0 <= index.column() < len(_COLUMNS):
            return None
        status = self.status_at(index.row())
        if status is None:
            return None
        if role == _DISPLAY_ROLE:
            match index.column():
                case 0:
                    return status.name
                case 1:
                    return _format_interval(status.interval)
                case 2:
                    return _state_badge(status.state)
                case 3:
                    if status.last_check is None:
                        return "never"
                    return format_time(status.last_check)
        elif role == _FOREGROUND_ROLE and index.column() == 2:
            return _state_colour(status.state)
        return None

    def status_at(self, row: int) -> WatcherStatus | None:
        """Return the status shown at a row.

        Args:
            row: Zero-based row index.

        Returns:
            The watcher's status, or None when the row is out of bounds.
        """
        if 0 <= row < len(self._statuses):
            return list(self._statuses.values())[row]
        return None

    def set_statuses(self, statuses: list[WatcherStatus]) -> None:
        """Replace all rows, e.g. with the statuses read when the window opens.

        Args:
            statuses: One status per watcher.
        """
        self.beginResetModel()
        self._statuses = {s.name: s for s in statuses}
        self.endResetModel()

    def update_state(self, changed: WatcherStateChanged) -> None:
        """Show a watcher's new state.

        Args:
            changed: Event published when the watcher changed state.
        """
        name = changed.watcher_name
        if name not in self._statuses:
            return
        self._statuses[name] = replace(self._statuses[name], state=changed.new_state)
        self._emit_data_changed(name, 2, [_DISPLAY_ROLE, _FOREGROUND_ROLE])

    def update_last_check(self, check: CheckCompleted) -> None:
        """Show when a watcher was last checked.

        Args:
            check: Event published at the end of the check.
        """
        name = check.watcher_name
        if name not in self._statuses:
            return
        self._statuses[name] = replace(self._statuses[name], last_check=check.timestamp)
        self._emit_data_changed(name, 3, [_DISPLAY_ROLE])

    def _emit_data_changed(self, name: str, column: int, roles: list[int]) -> None:
        """Tell attached views that one cell of a watcher changed.

        Args:
            name: Name of the watcher whose cell changed.
            column: Index of the changed column.
            roles: Roles whose values changed.
        """
        row = list(self._statuses).index(name)
        cell = self.index(row, column)
        self.dataChanged.emit(cell, cell, roles)


class WatchersTab(QWidget):
    """Table of watchers; its buttons send commands with `Scheduler.submit`."""

    def __init__(
        self,
        bridge: EngineBridge,
        scheduler: Scheduler,
        statuses: list[WatcherStatus] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize WatchersTab.

        Args:
            bridge: Signals of the running engine.
            scheduler: Scheduler to send commands to.
            statuses: Statuses read before the engine started; None when the
                tab is built on its own, outside `run_gui`.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self._scheduler = scheduler
        layout = QVBoxLayout(self)

        self._model = WatchersTableModel(self)
        self._model.set_statuses(initial_statuses(scheduler, statuses))

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
        selection = self._table.selectionModel()
        rows = selection.selectedRows() if selection is not None else []
        if not rows:
            return None
        status = self._model.status_at(rows[0].row())
        return None if status is None else status.name
