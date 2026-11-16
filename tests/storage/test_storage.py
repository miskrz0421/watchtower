"""Tests for SnapshotStore."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from watchtower.errors import StorageError
from watchtower.models import Item, Snapshot
from watchtower.storage.snapshots import SnapshotStore


def make_snapshot(*titles: str, raw_text: str = "page") -> Snapshot:
    """Build a snapshot with one item per title."""
    items = tuple(
        Item(key=str(number), title=title, url=f"http://test/{number}", price=1000.0 * number)
        for number, title in enumerate(titles, start=1)
    )
    return Snapshot(items=items, raw_text=raw_text, taken_at=datetime(2026, 11, 8, 12, tzinfo=UTC))


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """Store in a fresh database file."""
    return SnapshotStore(tmp_path / "watchtower.db")


def test_unknown_watcher_has_no_snapshot(store: SnapshotStore) -> None:
    """Test that a watcher that never saved gets None, the first-run baseline case."""
    assert store.load("never saved") is None


def test_saved_snapshot_loads_back_equal(store: SnapshotStore) -> None:
    """Test that items, raw text and time survive the JSON round trip."""
    snapshot = make_snapshot("Flat Krowodrza", "Studio Kazimierz", raw_text="zażółć <html>")

    store.save("flats", snapshot)

    assert store.load("flats") == snapshot


def test_save_replaces_previous_snapshot(store: SnapshotStore) -> None:
    """Test that only the last snapshot of a watcher is kept."""
    store.save("flats", make_snapshot("Old flat"))
    store.save("flats", make_snapshot("New flat"))

    loaded = store.load("flats")

    assert loaded is not None
    assert [item.title for item in loaded.items] == ["New flat"]


def test_watchers_are_stored_separately(store: SnapshotStore) -> None:
    """Test that saving one watcher does not touch another."""
    store.save("flats", make_snapshot("Flat"))
    store.save("news", make_snapshot("Scholarship news"))

    flats, news = store.load("flats"), store.load("news")

    assert flats is not None
    assert news is not None
    assert flats.items[0].title == "Flat"
    assert news.items[0].title == "Scholarship news"


def test_snapshot_survives_new_store_instance(tmp_path: Path) -> None:
    """Test that the data lives in the file, so it survives a program restart."""
    path = tmp_path / "watchtower.db"
    snapshot = make_snapshot("Flat")
    SnapshotStore(path).save("flats", snapshot)

    assert SnapshotStore(path).load("flats") == snapshot


def test_timezone_is_kept(store: SnapshotStore) -> None:
    """Test that a non-UTC offset is not lost or shifted."""
    warsaw = timezone(timedelta(hours=1))
    snapshot = Snapshot(raw_text="page", taken_at=datetime(2026, 11, 8, 13, tzinfo=warsaw))

    store.save("flats", snapshot)
    loaded = store.load("flats")

    assert loaded is not None
    assert loaded.taken_at.utcoffset() == timedelta(hours=1)


def test_unopenable_database_raises_storage_error(tmp_path: Path) -> None:
    """Test that a path in a missing folder gives a clear StorageError."""
    with pytest.raises(StorageError, match="Cannot open snapshot database"):
        SnapshotStore(tmp_path / "missing" / "watchtower.db")


def test_corrupted_data_raises_storage_error(tmp_path: Path) -> None:
    """Test that invalid saved JSON is reported, not passed on as a broken snapshot."""
    path = tmp_path / "watchtower.db"
    SnapshotStore(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO snapshots VALUES ('flats', '{not json')")
    conn.close()

    with pytest.raises(StorageError, match="invalid"):
        SnapshotStore(path).load("flats")
