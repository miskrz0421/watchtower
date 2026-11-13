"""Tests for the Watcher pipeline."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from watchtower.core.watcher import Watcher
from watchtower.diffs.text import TextDiff
from watchtower.errors import SourceError
from watchtower.events import ChangeDetected, CheckCompleted, EventBus, FetchFailed
from watchtower.models import ChangeEvent, Snapshot
from watchtower.notifiers.base import Notifier
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource
from watchtower.storage.snapshots import SnapshotStore


class FailingSource(Source):
    """Source that simulates runtime failure."""

    def fetch(self) -> str:
        """Fail with a SourceError."""
        msg = "Fetch timeout error"
        raise SourceError(msg)

    def parse(self, raw: str) -> list[None]:
        """Return no items; never reached."""
        return []


def test_watcher_check_once_end_to_end() -> None:
    """Test full pipeline execution: first check baseline, second check detects change."""
    source = FakeSource(contents=["version 1\n", "version 2\n"])
    differ = TextDiff()
    out = io.StringIO()
    notifier = ConsoleNotifier(stream=out)
    bus = EventBus()

    checks: list[CheckCompleted] = []
    changes: list[ChangeDetected] = []

    bus.subscribe(CheckCompleted, checks.append)
    bus.subscribe(ChangeDetected, changes.append)

    watcher = Watcher(
        name="test_watcher",
        source=source,
        differ=differ,
        notifiers=[notifier],
        event_bus=bus,
    )

    # First check: baseline established, no changes detected (ADR-004)
    event1 = watcher.check_once()
    assert event1 is None
    assert len(checks) == 1
    assert checks[0].ok is True
    assert len(changes) == 0
    assert out.getvalue() == ""

    # Second check: change detected and sent to notifier and bus
    event2 = watcher.check_once()
    assert event2 is not None
    assert len(checks) == 2
    assert checks[1].ok is True
    assert len(changes) == 1
    assert "-version 1" in out.getvalue()
    assert "+version 2" in out.getvalue()


def test_watcher_error_handling_and_event_publishing() -> None:
    """Test that errors publish CheckCompleted(ok=False) and FetchFailed events."""
    source = FailingSource()
    differ = TextDiff()
    bus = EventBus()

    failed_checks: list[CheckCompleted] = []
    fetch_fails: list[FetchFailed] = []

    bus.subscribe(CheckCompleted, failed_checks.append)
    bus.subscribe(FetchFailed, fetch_fails.append)

    watcher = Watcher(
        name="failing_watcher",
        source=source,
        differ=differ,
        event_bus=bus,
    )

    with pytest.raises(SourceError, match="Fetch timeout error"):
        watcher.check_once()

    assert len(failed_checks) == 1
    assert failed_checks[0].ok is False
    assert "Fetch timeout error" in (failed_checks[0].error or "")
    assert len(fetch_fails) == 1
    assert "Fetch timeout error" in fetch_fails[0].error


def test_watcher_properties_and_encapsulation() -> None:
    """Test that Watcher exposes read-only properties for its pipeline components."""
    source = FakeSource(contents=["version 1\n"])
    differ = TextDiff()
    notifier = ConsoleNotifier()
    bus = EventBus()
    watcher = Watcher(
        name="props_watcher",
        source=source,
        differ=differ,
        notifiers=[notifier],
        event_bus=bus,
    )
    assert watcher.name == "props_watcher"
    assert watcher.source is source
    assert watcher.differ is differ
    assert watcher.notifiers == [notifier]
    assert watcher.event_bus is bus
    assert watcher.store is None
    assert watcher.last_snapshot is None

    # Verify attributes cannot be directly reassigned (read-only properties)
    with pytest.raises(AttributeError):
        watcher.name = "new_name"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        watcher.source = source  # type: ignore[misc]


class RecordingNotifier(Notifier):
    """Notifier that keeps every event it receives."""

    def __init__(self) -> None:
        """Start with no received events."""
        self.events: list[ChangeEvent] = []

    def send(self, event: ChangeEvent) -> None:
        """Record the event."""
        self.events.append(event)


def make_watcher(store: SnapshotStore, *pages: str, notifier: Notifier | None = None) -> Watcher:
    """Build a text watcher named 'page' that replays the given pages."""
    return Watcher(
        name="page",
        source=FakeSource(contents=list(pages)),
        differ=TextDiff(),
        notifiers=[notifier or RecordingNotifier()],
        store=store,
    )


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """Store in a fresh database file."""
    return SnapshotStore(tmp_path / "watchtower.db")


def test_first_check_saves_baseline(store: SnapshotStore) -> None:
    """Test that the first check reports nothing but saves its snapshot (ADR-004)."""
    watcher = make_watcher(store, "version 1\n")

    assert watcher.check_once() is None
    assert store.load("page") == watcher.last_snapshot


def test_restart_with_same_store_does_not_realert(store: SnapshotStore) -> None:
    """Test that a new Watcher continues from the saved snapshot, as after a restart."""
    make_watcher(store, "version 1\n").check_once()

    notifier = RecordingNotifier()
    assert make_watcher(store, "version 1\n", notifier=notifier).check_once() is None
    assert notifier.events == []


def test_restart_with_same_store_detects_change(store: SnapshotStore) -> None:
    """Test that a change made while the program was not running is reported."""
    make_watcher(store, "version 1\n").check_once()

    event = make_watcher(store, "version 2\n").check_once()

    assert event is not None
    assert "+version 2" in (event.changes[0].diff_text or "")


def test_failed_fetch_keeps_saved_snapshot(store: SnapshotStore) -> None:
    """Test that a failing source does not overwrite the saved baseline."""
    make_watcher(store, "version 1\n").check_once()
    baseline = store.load("page")
    failing = Watcher(name="page", source=FailingSource(), differ=TextDiff(), store=store)

    with pytest.raises(SourceError):
        failing.check_once()

    assert store.load("page") == baseline


def test_snapshot_is_saved_after_notifying(store: SnapshotStore) -> None:
    """Test that notifiers run while the old snapshot is still saved (ADR-013)."""
    seen_during_send: list[Snapshot | None] = []

    class StoreCheckingNotifier(Notifier):
        def send(self, event: ChangeEvent) -> None:
            """Record what the store holds while notifiers are running."""
            seen_during_send.append(store.load("page"))

    make_watcher(store, "version 1\n").check_once()
    baseline = store.load("page")

    make_watcher(store, "version 2\n", notifier=StoreCheckingNotifier()).check_once()

    assert seen_during_send == [baseline]
    saved = store.load("page")
    assert saved is not None
    assert saved.raw_text == "version 2\n"
