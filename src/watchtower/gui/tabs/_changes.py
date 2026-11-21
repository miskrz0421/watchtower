"""Changes tab: every reported change, searchable, with the details of one."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from PySide6.QtCore import (
    QAbstractTableModel,
    QItemSelection,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from watchtower._events import ChangeDetected
from watchtower._models import Change
from watchtower.gui._bridge import EngineBridge
from watchtower.storage._history import ChangeRecord, HistoryStore

_COLUMNS: tuple[str, ...] = ("Time", "Watcher", "Kind", "Item", "Price")
_ROOT_INDEX = QModelIndex()


def _change_to_record(watcher_name: str, timestamp: datetime, change: Change) -> ChangeRecord:
    """Convert a Change from an event into a ChangeRecord.

    Args:
        watcher_name: Name of the watcher reporting the change.
        timestamp: Time when the change was detected.
        change: Change object from the event.

    Returns:
        A ChangeRecord representation.
    """
    item = change.item if change.item is not None else change.before
    return ChangeRecord(
        watcher_name=watcher_name,
        timestamp=timestamp,
        kind=change.kind,
        key=item.key if item is not None else None,
        title=item.title if item is not None else None,
        price=change.item.price if change.item is not None else None,
        old_price=change.before.price if change.before is not None else None,
        diff_text=change.diff_text,
    )


def _format_item(record: ChangeRecord) -> str:
    """Return a display string for the item title, key, or text diff.

    Args:
        record: ChangeRecord to extract item description from.

    Returns:
        Title, key, '(text diff)', or an empty string.
    """
    return record.title or record.key or ("(text diff)" if record.diff_text else "")


def _format_price(record: ChangeRecord) -> str:
    """Return a display string for the price or price change.

    Args:
        record: ChangeRecord to extract price from.

    Returns:
        Formatted price transition, current price, or an empty string.
    """
    if record.price is not None and record.old_price is not None:
        return f"{record.old_price} -> {record.price}"
    if record.price is not None:
        return str(record.price)
    if record.old_price is not None:
        return f"(was {record.old_price})"
    return ""


def _format_details(record: ChangeRecord) -> str:
    """Format a ChangeRecord into readable details text.

    Args:
        record: ChangeRecord to format.

    Returns:
        Formatted summary string including diff text if present.
    """
    lines = [
        f"Watcher: {record.watcher_name}",
        f"Timestamp: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Kind: {record.kind.value}",
    ]
    if record.key:
        lines.append(f"Key: {record.key}")
    if record.title:
        lines.append(f"Title: {record.title}")
    price_str = _format_price(record)
    if price_str:
        lines.append(f"Price: {price_str}")
    if record.diff_text:
        lines.append("")
        lines.append("--- Diff ---")
        lines.append(record.diff_text)
    return "\n".join(lines)


class ChangesTableModel(QAbstractTableModel):
    """One row per reported change, newest first."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize ChangesTableModel.

        Args:
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._rows: list[ChangeRecord] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        """Return the number of rows in the model.

        Args:
            parent: Parent model index.

        Returns:
            Number of change records.
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
        role: int = int(Qt.ItemDataRole.DisplayRole),
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
            and role == int(Qt.ItemDataRole.DisplayRole)
            and 0 <= section < len(_COLUMNS)
        ):
            return _COLUMNS[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> str | None:
        """Return display data for a given model index.

        Args:
            index: Model index requesting data.
            role: Data role being queried.

        Returns:
            Cell data for DisplayRole, or None.
        """
        if not index.isValid() or role != int(Qt.ItemDataRole.DisplayRole):
            return None
        record = self._record_at(index.row())
        if record is None:
            return None
        match index.column():
            case 0:
                return record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            case 1:
                return record.watcher_name
            case 2:
                return record.kind.value
            case 3:
                return _format_item(record)
            case 4:
                return _format_price(record)
            case _:
                return None

    def _record_at(self, row: int) -> ChangeRecord | None:
        """Return the change record at the given row index.

        Args:
            row: Zero-based row index.

        Returns:
            The ChangeRecord, or None if the index is out of bounds.
        """
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def load(self, records: Iterable[ChangeRecord]) -> None:
        """Replace all rows with changes read from the history.

        Args:
            records: Saved changes, oldest first, as `HistoryStore.changes()` yields them.
        """
        self.beginResetModel()
        self._rows = list(records)
        self._rows.reverse()
        self.endResetModel()

    def add_event(self, detected: ChangeDetected) -> None:
        """Add a row for each change of a new event.

        Args:
            detected: Event published when a check found changes.
        """
        new_records = [
            _change_to_record(detected.watcher_name, detected.event.timestamp, change)
            for change in detected.event.changes
        ]
        if not new_records:
            return
        self.beginInsertRows(QModelIndex(), 0, len(new_records) - 1)
        self._rows[0:0] = new_records
        self.endInsertRows()


class ChangesTab(QWidget):
    """Search box, table of changes and the details of the selected one."""

    def __init__(
        self, bridge: EngineBridge, history: HistoryStore | None, parent: QWidget | None = None
    ) -> None:
        """Initialize ChangesTab.

        Args:
            bridge: Signals of the running engine.
            history: Saved changes to show first; None when the config has no database.
            parent: Qt parent widget.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self._model = ChangesTableModel(self)
        if history is not None:
            self._model.load(history.changes())

        bridge.change_detected.connect(self._model.add_event)

        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText("Search changes...")
        self._search_box.setClearButtonEnabled(True)
        layout.addWidget(self._search_box)

        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterKeyColumn(-1)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._search_box.textChanged.connect(self._on_search_changed)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        layout.addWidget(splitter)

        self._table = QTableView(self)
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        header = self._table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        splitter.addWidget(self._table)

        self._details = QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._details.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._details.setPlaceholderText("Select a change to view details or diff...")
        splitter.addWidget(self._details)

        selection_model = self._table.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self._on_selection_changed)

    def _on_search_changed(self, text: str) -> None:
        """Filter table rows matching the search text.

        Args:
            text: Query string to match against any column.
        """
        self._proxy.setFilterFixedString(text)

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        _deselected: QItemSelection,
    ) -> None:
        """Update the details text box with the selected change's details or diff.

        Args:
            selected: Selected item indexes.
            _deselected: Deselected item indexes.
        """
        indexes = selected.indexes()
        if not indexes:
            self._details.clear()
            return
        source_index = self._proxy.mapToSource(indexes[0])
        record = self._model._record_at(source_index.row())
        if record is None:
            self._details.clear()
            return
        self._details.setPlainText(_format_details(record))
