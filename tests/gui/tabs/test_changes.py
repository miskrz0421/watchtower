"""Tests for ChangesTableModel and ChangesTab."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTableView
from pytestqt.qtbot import QtBot

from watchtower import Change, ChangeDetected, ChangeEvent, ChangeKind, Item
from watchtower.gui import EngineBridge
from watchtower.gui.tabs import ChangesTab, ChangesTableModel
from watchtower.gui.tabs._changes import _format_price
from watchtower.storage import ChangeRecord, HistoryStore

pytestmark = pytest.mark.gui


def test_model_empty_on_creation() -> None:
    """Test that a new ChangesTableModel is empty with valid column headers."""
    model = ChangesTableModel()

    assert model.rowCount() == 0
    assert model.columnCount() == 5
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Time"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Watcher"
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Kind"
    assert model.headerData(3, Qt.Orientation.Horizontal) == "Item"
    assert model.headerData(4, Qt.Orientation.Horizontal) == "Price"
    assert model.headerData(5, Qt.Orientation.Horizontal) is None
    assert model.headerData(0, Qt.Orientation.Vertical) is None
    assert model.data(model.index(0, 0)) is None
    assert model.record_at(0) is None


def test_model_load_from_history_reverses_order_to_newest_first(tmp_path: Path) -> None:
    """Test that loading from HistoryStore displays rows newest first."""
    store = HistoryStore(tmp_path / "history.db")
    t1 = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 15, 11, 0, tzinfo=UTC)

    store.record_changes(
        ChangeEvent(
            watcher_name="w1",
            timestamp=t1,
            changes=(Change(kind=ChangeKind.NEW, item=Item(key="k1", title="First Item")),),
            summary="1 new item",
        )
    )
    store.record_changes(
        ChangeEvent(
            watcher_name="w2",
            timestamp=t2,
            changes=(
                Change(
                    kind=ChangeKind.CHANGED,
                    item=Item(key="k2", title="Second Item", price=250.0),
                    before=Item(key="k2", title="Second Item", price=300.0),
                ),
            ),
            summary="1 price changed",
        )
    )

    model = ChangesTableModel()
    model.load(store.changes())

    assert model.rowCount() == 2
    # Row 0 is the newest (w2 at 11:00)
    assert model.data(model.index(0, 1)) == "w2"
    assert model.data(model.index(0, 2)) == "changed"
    assert model.data(model.index(0, 3)) == "Second Item"
    assert model.data(model.index(0, 4)) == "300 zł → 250 zł"

    # Row 1 is the oldest (w1 at 10:00)
    assert model.data(model.index(1, 1)) == "w1"
    assert model.data(model.index(1, 2)) == "new"
    assert model.data(model.index(1, 3)) == "First Item"


def test_model_displays_timestamps_in_local_timezone() -> None:
    """Test that the Time column converts UTC timestamps to local time."""
    utc_time = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    expected_local = utc_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    model = ChangesTableModel()
    model.load(
        [
            ChangeRecord(
                watcher_name="w1",
                timestamp=utc_time,
                kind=ChangeKind.NEW,
                key="k1",
                title="Item",
                price=None,
                old_price=None,
            )
        ]
    )

    assert model.data(model.index(0, 0)) == expected_local


def test_model_add_event_inserts_row_at_top() -> None:
    """Test that add_event inserts incoming live changes at the top of the table."""
    model = ChangesTableModel()
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    model.load(
        [
            ChangeRecord(
                watcher_name="w1",
                timestamp=now - timedelta(hours=1),
                kind=ChangeKind.NEW,
                key="k1",
                title="Older",
                price=None,
                old_price=None,
            )
        ]
    )

    detected = ChangeDetected(
        watcher_name="w2",
        event=ChangeEvent(
            watcher_name="w2",
            timestamp=now,
            changes=(Change(kind=ChangeKind.TEXT, diff_text="@@ -1 +1 @@\n-a\n+b"),),
            summary="text diff",
        ),
    )
    model.add_event(detected)

    assert model.rowCount() == 2
    assert model.data(model.index(0, 1)) == "w2"
    assert model.data(model.index(0, 2)) == "text"
    assert model.data(model.index(0, 3)) == "(text diff)"
    record = model.record_at(0)
    assert record is not None
    assert record.diff_text == "@@ -1 +1 @@\n-a\n+b"


def test_model_add_empty_event_does_nothing() -> None:
    """Test that add_event with no changes does not insert any rows."""
    model = ChangesTableModel()
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    empty_detected = ChangeDetected(
        watcher_name="w1",
        event=ChangeEvent(watcher_name="w1", timestamp=now, changes=(), summary="empty"),
    )
    model.add_event(empty_detected)

    assert model.rowCount() == 0


def test_format_price_handles_all_price_variants() -> None:
    """Test that _format_price formats transitions, current, removed and missing prices."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    changed = ChangeRecord("w", now, ChangeKind.CHANGED, "k", "t", price=250.0, old_price=300.0)
    assert _format_price(changed) == "300 zł → 250 zł"

    decimal_changed = ChangeRecord(
        "w", now, ChangeKind.CHANGED, "k", "t", price=2400.5, old_price=2800.0
    )
    assert _format_price(decimal_changed) == "2 800 zł → 2 400,50 zł"

    new_item = ChangeRecord("w", now, ChangeKind.NEW, "k", "t", price=50.0, old_price=None)
    assert _format_price(new_item) == "50 zł"

    removed = ChangeRecord("w", now, ChangeKind.REMOVED, "k", "t", price=None, old_price=40.0)
    assert _format_price(removed) == "(was 40 zł)"

    no_price = ChangeRecord("w", now, ChangeKind.TEXT, None, None, price=None, old_price=None)
    assert _format_price(no_price) == ""


def test_change_record_from_change_factory() -> None:
    """Test that ChangeRecord.from_change populates all fields accurately."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    change = Change(
        kind=ChangeKind.CHANGED,
        item=Item(key="k1", title="Title", price=20.0),
        before=Item(key="k1", title="Title", price=25.0),
        diff_text="diff",
    )
    record = ChangeRecord.from_change("watcher", now, change)

    assert record == ChangeRecord(
        watcher_name="watcher",
        timestamp=now,
        kind=ChangeKind.CHANGED,
        key="k1",
        title="Title",
        price=20.0,
        old_price=25.0,
        diff_text="diff",
    )


def test_tab_loads_history_and_updates_on_bridge_signal(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that ChangesTab loads history on init and updates on bridge.change_detected."""
    store = HistoryStore(tmp_path / "history.db")
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    store.record_changes(
        ChangeEvent(
            watcher_name="flats",
            timestamp=now,
            changes=(Change(kind=ChangeKind.NEW, item=Item(key="f1", title="Studio")),),
            summary="new studio",
        )
    )

    bridge = EngineBridge()
    tab = ChangesTab(bridge, store)
    qtbot.addWidget(tab)

    table = tab.findChild(QTableView)
    assert table is not None
    assert table.model().rowCount() == 1

    # Emit bridge signal from engine simulation
    live_event = ChangeEvent(
        watcher_name="news",
        timestamp=now + timedelta(minutes=5),
        changes=(Change(kind=ChangeKind.NEW, item=Item(key="n1", title="Breaking News")),),
        summary="new news",
    )
    bridge.change_detected.emit(
        ChangeDetected(watcher_name="news", event=live_event, timestamp=live_event.timestamp)
    )

    assert table.model().rowCount() == 2
    assert table.model().data(table.model().index(0, 1)) == "news"


def test_tab_without_history(qtbot: QtBot) -> None:
    """Test that ChangesTab works correctly when history is None."""
    bridge = EngineBridge()
    tab = ChangesTab(bridge, history=None)
    qtbot.addWidget(tab)

    table = tab.findChild(QTableView)
    assert table is not None
    assert table.model().rowCount() == 0

    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    live_event = ChangeEvent(
        watcher_name="flats",
        timestamp=now,
        changes=(Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat")),),
        summary="new flat",
    )
    bridge.change_detected.emit(
        ChangeDetected(watcher_name="flats", event=live_event, timestamp=now)
    )

    assert table.model().rowCount() == 1


def test_search_box_filters_rows_case_insensitively(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that the search box filters rows across columns using the proxy model."""
    store = HistoryStore(tmp_path / "history.db")
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    store.record_changes(
        ChangeEvent(
            watcher_name="flats",
            timestamp=now,
            changes=(Change(kind=ChangeKind.NEW, item=Item(key="f1", title="Center Apartment")),),
            summary="center apartment",
        )
    )
    store.record_changes(
        ChangeEvent(
            watcher_name="crypto",
            timestamp=now + timedelta(minutes=1),
            changes=(
                Change(
                    kind=ChangeKind.CHANGED,
                    item=Item(key="btc", title="Bitcoin", price=95000.0),
                ),
            ),
            summary="bitcoin update",
        )
    )

    tab = ChangesTab(EngineBridge(), store)
    qtbot.addWidget(tab)

    table = tab.findChild(QTableView)
    search_box = tab.findChild(QLineEdit)
    assert table is not None and search_box is not None
    proxy = table.model()

    assert proxy.rowCount() == 2

    # Filter by watcher name (case-insensitive)
    search_box.setText("crypto")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "crypto"

    search_box.setText("CRYPTO")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "crypto"

    # Filter by title (case-insensitive)
    search_box.setText("center")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "flats"

    search_box.setText("CENTER")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "flats"

    # Filter with no match
    search_box.setText("nonexistent")
    assert proxy.rowCount() == 0

    # Clear filter
    search_box.setText("")
    assert proxy.rowCount() == 2


def test_selecting_row_displays_item_details(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that selecting an item change displays formatted metadata and price transition."""
    store = HistoryStore(tmp_path / "history.db")
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    store.record_changes(
        ChangeEvent(
            watcher_name="shop",
            timestamp=now,
            changes=(
                Change(
                    kind=ChangeKind.CHANGED,
                    item=Item(key="p1", title="Shoes", price=80.0),
                    before=Item(key="p1", title="Shoes", price=100.0),
                ),
            ),
            summary="price dropped",
        )
    )

    tab = ChangesTab(EngineBridge(), store)
    qtbot.addWidget(tab)

    table = tab.findChild(QTableView)
    details = tab.findChild(QPlainTextEdit)
    assert table is not None and details is not None

    table.selectRow(0)
    text = details.toPlainText()
    assert "Watcher: shop" in text
    assert "Title: Shoes" in text
    assert "Price: 100 zł → 80 zł" in text


def test_selecting_row_displays_diff_details(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that selecting a text change displays the formatted unified diff."""
    store = HistoryStore(tmp_path / "history.db")
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    diff = "--- old\n+++ new\n@@ -1 +1 @@\n-red\n+blue\n"
    store.record_changes(
        ChangeEvent(
            watcher_name="site",
            timestamp=now,
            changes=(Change(kind=ChangeKind.TEXT, diff_text=diff),),
            summary="text diff",
        )
    )

    tab = ChangesTab(EngineBridge(), store)
    qtbot.addWidget(tab)

    table = tab.findChild(QTableView)
    details = tab.findChild(QPlainTextEdit)
    assert table is not None and details is not None

    table.selectRow(0)
    text = details.toPlainText()
    assert "Watcher: site" in text
    assert "Kind: text" in text
    assert "--- Diff ---" in text
    assert "+blue" in text


def test_clearing_selection_clears_details(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that deselecting rows clears the details panel."""
    store = HistoryStore(tmp_path / "history.db")
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    store.record_changes(
        ChangeEvent(
            watcher_name="site",
            timestamp=now,
            changes=(Change(kind=ChangeKind.TEXT, diff_text="diff"),),
            summary="diff",
        )
    )

    tab = ChangesTab(EngineBridge(), store)
    qtbot.addWidget(tab)

    table = tab.findChild(QTableView)
    details = tab.findChild(QPlainTextEdit)
    assert table is not None and details is not None

    table.selectRow(0)
    assert details.toPlainText() != ""

    table.clearSelection()
    assert details.toPlainText() == ""
