"""Tests for WatcherBuilder."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from watchtower.core.builder import WatcherBuilder
from watchtower.core.watcher import DEFAULT_INTERVAL
from watchtower.diffs.text import TextDiff
from watchtower.errors import ConfigError
from watchtower.events import EventBus
from watchtower.filters.base import Filter
from watchtower.models import Change, ChangeEvent
from watchtower.notifiers.base import Notifier
from watchtower.sources.fake import FakeSource
from watchtower.storage.snapshots import SnapshotStore


class _AcceptAll(Filter):
    """Filter accepting every change."""

    def matches(self, change: Change) -> bool:
        """Accept the change."""
        return True


class _RejectAll(Filter):
    """Filter rejecting every change."""

    def matches(self, change: Change) -> bool:
        """Reject the change."""
        return False


class _RecordingNotifier(Notifier):
    """Notifier that keeps every event it receives."""

    def __init__(self) -> None:
        """Start with no received events."""
        self.events: list[ChangeEvent] = []

    def send(self, event: ChangeEvent) -> None:
        """Record the event."""
        self.events.append(event)


def _text_builder(*pages: str) -> WatcherBuilder:
    """Return a builder for a text watcher named 'page' that replays the given pages."""
    return WatcherBuilder("page").source(FakeSource(contents=list(pages))).diff(TextDiff())


def test_build_passes_every_part_to_the_watcher(tmp_path: Path) -> None:
    """Test that each chained step ends up on the built watcher."""
    source = FakeSource()
    differ = TextDiff()
    accept = _AcceptAll()
    notifier = _RecordingNotifier()
    store = SnapshotStore(tmp_path / "state.db")
    bus = EventBus()

    watcher = (
        WatcherBuilder("Flats")
        .source(source)
        .every(timedelta(seconds=30))
        .diff(differ)
        .only_if(accept)
        .notify(notifier)
        .store(store)
        .event_bus(bus)
        .build()
    )

    assert watcher.name == "Flats"
    assert watcher.source is source
    assert watcher.differ is differ
    assert watcher.interval == timedelta(seconds=30)
    assert watcher.filters == [accept]
    assert watcher.notifiers == [notifier]
    assert watcher.store is store
    assert watcher.event_bus is bus


def test_optional_parts_have_defaults() -> None:
    """Test that only the source and the differ are required."""
    watcher = _text_builder().build()

    assert watcher.interval == DEFAULT_INTERVAL
    assert watcher.filters == []
    assert watcher.notifiers == []
    assert watcher.store is None
    assert watcher.event_bus is None


def test_filters_and_notifiers_add_up_over_several_calls() -> None:
    """Test that only_if and notify append instead of replacing."""
    accept, reject = _AcceptAll(), _RejectAll()
    first, second = _RecordingNotifier(), _RecordingNotifier()

    watcher = _text_builder().only_if(accept).only_if(reject).notify(first, second).build()

    assert watcher.filters == [accept, reject]
    assert watcher.notifiers == [first, second]


def test_each_build_gives_a_separate_watcher() -> None:
    """Test that two watchers from one builder do not share their state."""
    builder = _text_builder("version 1\n")
    first = builder.build()
    second = builder.build()

    first.check_once()

    assert first is not second
    assert first.last_snapshot is not None
    assert second.last_snapshot is None


def test_build_without_source_names_the_watcher() -> None:
    """Test that a missing source is reported with the watcher's name."""
    builder = WatcherBuilder("Flats").diff(TextDiff())

    with pytest.raises(ConfigError, match="'Flats' has no source"):
        builder.build()


def test_build_without_differ_names_the_watcher() -> None:
    """Test that a missing differ is reported with the watcher's name."""
    builder = WatcherBuilder("Flats").source(FakeSource())

    with pytest.raises(ConfigError, match="'Flats' has no differ"):
        builder.build()


@pytest.mark.parametrize("interval", [timedelta(0), timedelta(seconds=-5)])
def test_interval_must_be_positive(interval: timedelta) -> None:
    """Test that a zero or negative interval is rejected."""
    with pytest.raises(ConfigError, match="interval must be positive"):
        WatcherBuilder("Flats").every(interval)


def test_built_watcher_applies_its_filters() -> None:
    """Test that a built watcher runs and reports only changes its filters accept."""
    accepted, rejected = _RecordingNotifier(), _RecordingNotifier()
    watchers = [
        _text_builder("v1\n", "v2\n").only_if(_AcceptAll()).notify(accepted).build(),
        _text_builder("v1\n", "v2\n").only_if(_RejectAll()).notify(rejected).build(),
    ]

    for watcher in watchers:
        watcher.check_once()
        watcher.check_once()

    assert len(accepted.events) == 1
    assert rejected.events == []
