"""Tests for HistoryRecorder."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from watchtower import (
    Change,
    ChangeDetected,
    ChangeEvent,
    ChangeKind,
    CheckCompleted,
    EventBus,
    FetchFailed,
    Item,
)
from watchtower.storage import HistoryRecorder, HistoryStore


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    """Create a HistoryStore in a temporary database file."""
    return HistoryStore(tmp_path / "history.db")


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
