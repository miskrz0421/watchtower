"""Tests for HistoryStore and HistoryRecorder."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from watchtower.errors import StorageError
from watchtower.events import ChangeDetected, CheckCompleted, EventBus, FetchFailed
from watchtower.models import Change, ChangeEvent, ChangeKind, Item, Snapshot
from watchtower.storage.history import ChangeRecord, CheckRecord, HistoryStore
from watchtower.storage.recorder import HistoryRecorder
from watchtower.storage.snapshots import SnapshotStore


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    """Create a HistoryStore in a temporary database file."""
    return HistoryStore(tmp_path / "history.db")


def test_empty_store_yields_nothing(store: HistoryStore) -> None:
    """Test that a new store yields no changes and no checks."""
    assert list(store.changes()) == []
    assert list(store.checks()) == []


def test_record_changes_and_read_back(store: HistoryStore) -> None:
    """Test that recorded changes survive round trip with exact fields."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    item = Item(key="k1", title="Flat in center", price=3200.0)
    old_item = Item(key="k1", title="Flat in center", price=3500.0)
    change = Change(kind=ChangeKind.CHANGED, item=item, before=old_item)
    event = ChangeEvent(
        watcher_name="flats",
        timestamp=now,
        changes=(change,),
        summary="1 change detected",
    )

    store.record_changes(event)
    records = list(store.changes())

    assert len(records) == 1
    record = records[0]
    assert record == ChangeRecord(
        watcher_name="flats",
        timestamp=now,
        kind=ChangeKind.CHANGED,
        key="k1",
        title="Flat in center",
        price=3200.0,
        old_price=3500.0,
    )


def test_record_changes_without_item(store: HistoryStore) -> None:
    """Test recording text diff changes where item is None."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    change = Change(kind=ChangeKind.TEXT, diff_text="line changed")
    event = ChangeEvent(
        watcher_name="page",
        timestamp=now,
        changes=(change,),
        summary="text changed",
    )

    store.record_changes(event)
    records = list(store.changes())

    assert len(records) == 1
    assert records[0].kind == ChangeKind.TEXT
    assert records[0].key is None
    assert records[0].title is None
    assert records[0].price is None
    assert records[0].old_price is None


def test_record_changes_with_empty_event_does_nothing(store: HistoryStore) -> None:
    """Test that recording an event with no changes writes no rows."""
    event = ChangeEvent(
        watcher_name="flats",
        timestamp=datetime.now(UTC),
        changes=(),
        summary="no changes",
    )

    store.record_changes(event)

    assert list(store.changes()) == []


def test_changes_filtering_by_watcher(store: HistoryStore) -> None:
    """Test filtering changes by watcher name."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    item1 = Item(key="1", title="Offer 1")
    item2 = Item(key="2", title="News 1")

    store.record_changes(
        ChangeEvent(
            watcher_name="flats",
            timestamp=now,
            changes=(Change(kind=ChangeKind.NEW, item=item1),),
            summary="new",
        )
    )
    store.record_changes(
        ChangeEvent(
            watcher_name="news",
            timestamp=now,
            changes=(Change(kind=ChangeKind.NEW, item=item2),),
            summary="new",
        )
    )

    all_changes = list(store.changes())
    flats_changes = list(store.changes("flats"))
    news_changes = list(store.changes("news"))
    other_changes = list(store.changes("other"))

    assert len(all_changes) == 2
    assert [c.watcher_name for c in flats_changes] == ["flats"]
    assert [c.watcher_name for c in news_changes] == ["news"]
    assert other_changes == []


def test_record_check_and_read_back(store: HistoryStore) -> None:
    """Test that recorded checks survive round trip with exact fields."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    check_ok = CheckCompleted(
        watcher_name="flats",
        timestamp=now,
        duration_seconds=0.45,
        ok=True,
    )
    check_failed = CheckCompleted(
        watcher_name="news",
        timestamp=now + timedelta(seconds=1),
        duration_seconds=1.2,
        ok=False,
        error="HTTP 500",
    )

    store.record_check(check_ok)
    store.record_check(check_failed)
    records = list(store.checks())

    assert len(records) == 2
    assert records[0] == CheckRecord(
        watcher_name="flats",
        timestamp=now,
        ok=True,
        duration_seconds=0.45,
        error=None,
    )
    assert records[1] == CheckRecord(
        watcher_name="news",
        timestamp=now + timedelta(seconds=1),
        ok=False,
        duration_seconds=1.2,
        error="HTTP 500",
    )


def test_checks_filtering_by_watcher(store: HistoryStore) -> None:
    """Test filtering checks by watcher name."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    store.record_check(
        CheckCompleted(watcher_name="flats", timestamp=now, duration_seconds=0.1, ok=True)
    )
    store.record_check(
        CheckCompleted(watcher_name="news", timestamp=now, duration_seconds=0.2, ok=True)
    )

    flats_checks = list(store.checks("flats"))
    news_checks = list(store.checks("news"))
    other_checks = list(store.checks("missing"))

    assert [c.watcher_name for c in flats_checks] == ["flats"]
    assert [c.watcher_name for c in news_checks] == ["news"]
    assert other_checks == []


def test_changes_and_checks_ordered_oldest_first(store: HistoryStore) -> None:
    """Test that records are yielded in chronological insertion order."""
    base = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    for i in range(3):
        t = base + timedelta(minutes=i)
        store.record_check(
            CheckCompleted(watcher_name="w", timestamp=t, duration_seconds=0.1, ok=True)
        )
        item = Item(key=str(i), title=f"Item {i}")
        store.record_changes(
            ChangeEvent(
                watcher_name="w",
                timestamp=t,
                changes=(Change(kind=ChangeKind.NEW, item=item),),
                summary="new",
            )
        )

    checks = list(store.checks())
    changes = list(store.changes())

    assert [c.timestamp for c in checks] == [base + timedelta(minutes=i) for i in range(3)]
    assert [c.key for c in changes] == ["0", "1", "2"]


def test_history_shares_database_with_snapshot_store(tmp_path: Path) -> None:
    """Test that HistoryStore and SnapshotStore coexist in the same database file."""
    db_path = tmp_path / "shared.db"
    snapshots = SnapshotStore(db_path)
    history = HistoryStore(db_path)

    snapshot = Snapshot(raw_text="html", taken_at=datetime.now(UTC))
    snapshots.save("flats", snapshot)

    check = CheckCompleted(watcher_name="flats", duration_seconds=0.1, ok=True)
    history.record_check(check)

    assert snapshots.load("flats") == snapshot
    checks = list(history.checks("flats"))
    assert len(checks) == 1
    assert checks[0].watcher_name == "flats"


def test_unopenable_database_raises_storage_error(tmp_path: Path) -> None:
    """Test that a database in a missing directory raises StorageError."""
    with pytest.raises(StorageError, match="Cannot open history database"):
        HistoryStore(tmp_path / "missing_dir" / "history.db")


def test_corrupted_change_record_raises_storage_error(tmp_path: Path) -> None:
    """Test that invalid change row data raises StorageError."""
    db_path = tmp_path / "corrupted.db"
    store = HistoryStore(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO changes (watcher_name, timestamp, kind) VALUES (?, ?, ?)",
            ("flats", "not-a-timestamp", "new"),
        )

    with pytest.raises(StorageError, match="Saved change in .* is invalid"):
        list(store.changes())


def test_corrupted_check_record_raises_storage_error(tmp_path: Path) -> None:
    """Test that invalid check row data raises StorageError."""
    db_path = tmp_path / "corrupted.db"
    store = HistoryStore(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO checks (watcher_name, timestamp, ok, duration_seconds) "
            "VALUES (?, ?, ?, ?)",
            ("flats", "not-a-timestamp", 1, 0.5),
        )

    with pytest.raises(StorageError, match="Saved check in .* is invalid"):
        list(store.checks())


def test_recorder_with_real_event_bus(store: HistoryStore) -> None:
    """Test HistoryRecorder recording CheckCompleted and ChangeDetected from EventBus."""
    bus = EventBus()
    recorder = HistoryRecorder(store)
    recorder.attach(bus)

    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    check_event = CheckCompleted(watcher_name="flats", timestamp=now, duration_seconds=0.3, ok=True)
    change_event = ChangeEvent(
        watcher_name="flats",
        timestamp=now,
        changes=(Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat")),),
        summary="1 new item",
    )
    change_detected = ChangeDetected(watcher_name="flats", event=change_event, timestamp=now)
    unrelated_event = FetchFailed(watcher_name="flats", error="timeout", timestamp=now)

    bus.publish(unrelated_event)
    bus.publish(check_event)
    bus.publish(change_detected)

    checks = list(store.checks())
    changes = list(store.changes())

    assert len(checks) == 1
    assert checks[0].watcher_name == "flats"
    assert checks[0].ok is True
    assert len(changes) == 1
    assert changes[0].key == "1"
    assert changes[0].title == "Flat"


def test_history_database_execution_error_raises_storage_error(tmp_path: Path) -> None:
    """Test that SQLite errors during query execution raise StorageError."""
    db_path = tmp_path / "corrupted_exec.db"
    store = HistoryStore(db_path)
    with db_path.open("r+b") as f:
        f.seek(16)
        f.write(b"\xff" * 50)

    check = CheckCompleted(watcher_name="w", duration_seconds=0.1, ok=True)
    with pytest.raises(StorageError, match="History database .* failed"):
        store.record_check(check)
