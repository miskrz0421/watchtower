"""Tests for ChangesTableModel and ChangesTab."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from watchtower import Change, ChangeDetected, ChangeEvent, ChangeKind, Item
from watchtower.gui import EngineBridge
from watchtower.gui.tabs import ChangesTab, ChangesTableModel
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
    assert model._record_at(0) is None


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
    assert model.data(model.index(0, 4)) == "300.0 -> 250.0"

    # Row 1 is the oldest (w1 at 10:00)
    assert model.data(model.index(1, 1)) == "w1"
    assert model.data(model.index(1, 2)) == "new"
    assert model.data(model.index(1, 3)) == "First Item"


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
    record = model._record_at(0)
    assert record is not None
    assert record.diff_text == "@@ -1 +1 @@\n-a\n+b"

    # Empty event does not add rows
    empty_detected = ChangeDetected(
        watcher_name="w2",
        event=ChangeEvent(watcher_name="w2", timestamp=now, changes=(), summary="empty"),
    )
    model.add_event(empty_detected)
    assert model.rowCount() == 2


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

    assert tab._table.model().rowCount() == 1

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

    assert tab._table.model().rowCount() == 2
    assert tab._table.model().data(tab._table.model().index(0, 1)) == "news"


def test_tab_without_history(qtbot: QtBot) -> None:
    """Test that ChangesTab works correctly when history is None."""
    bridge = EngineBridge()
    tab = ChangesTab(bridge, history=None)
    qtbot.addWidget(tab)

    assert tab._table.model().rowCount() == 0

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

    assert tab._table.model().rowCount() == 1


def test_search_box_filters_rows(qtbot: QtBot, tmp_path: Path) -> None:
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

    assert tab._proxy.rowCount() == 2

    # Filter by watcher name (case-insensitive)
    tab._search_box.setText("crypto")
    assert tab._proxy.rowCount() == 1
    assert tab._proxy.data(tab._proxy.index(0, 1)) == "crypto"

    tab._search_box.setText("CRYPTO")
    assert tab._proxy.rowCount() == 1
    assert tab._proxy.data(tab._proxy.index(0, 1)) == "crypto"

    # Filter by title (case-insensitive)
    tab._search_box.setText("center")
    assert tab._proxy.rowCount() == 1
    assert tab._proxy.data(tab._proxy.index(0, 1)) == "flats"

    tab._search_box.setText("CENTER")
    assert tab._proxy.rowCount() == 1
    assert tab._proxy.data(tab._proxy.index(0, 1)) == "flats"

    # Filter with no match
    tab._search_box.setText("nonexistent")
    assert tab._proxy.rowCount() == 0

    # Clear filter
    tab._search_box.setText("")
    assert tab._proxy.rowCount() == 2


def test_selecting_row_displays_details_and_diff(qtbot: QtBot, tmp_path: Path) -> None:
    """Test that selecting a row shows formatted details and unified diff in the details box."""
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
    store.record_changes(
        ChangeEvent(
            watcher_name="shop",
            timestamp=now + timedelta(minutes=1),
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

    # Row 0 is the newest (shop)
    tab._table.selectRow(0)
    details_shop = tab._details.toPlainText()
    assert "Watcher: shop" in details_shop
    assert "Title: Shoes" in details_shop
    assert "Price: 100.0 -> 80.0" in details_shop

    # Row 1 is the oldest (site with diff)
    tab._table.selectRow(1)
    details_diff = tab._details.toPlainText()
    assert "Watcher: site" in details_diff
    assert "Kind: text" in details_diff
    assert "--- Diff ---" in details_diff
    assert "+blue" in details_diff

    # Clear selection clears details
    tab._table.clearSelection()
    assert tab._details.toPlainText() == ""

    # Test item with price but without old_price
    new_item = ChangeEvent(
        watcher_name="market",
        timestamp=now + timedelta(minutes=2),
        changes=(Change(kind=ChangeKind.NEW, item=Item(key="m1", title="Stock", price=50.0)),),
        summary="new stock",
    )
    tab._model.add_event(ChangeDetected(watcher_name="market", event=new_item, timestamp=now))
    tab._table.selectRow(0)
    assert "Price: 50.0" in tab._details.toPlainText()

    # Test item with old_price but without new price (removed item)
    removed_item = ChangeEvent(
        watcher_name="shop",
        timestamp=now + timedelta(minutes=3),
        changes=(Change(kind=ChangeKind.REMOVED, before=Item(key="hat", title="Hat", price=40.0)),),
        summary="hat removed",
    )
    tab._model.add_event(ChangeDetected(watcher_name="shop", event=removed_item, timestamp=now))
    tab._table.selectRow(0)
    assert "Price: (was 40.0)" in tab._details.toPlainText()
