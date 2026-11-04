"""Tests for EventBus and event dispatching."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from watchtower.events import (
    ChangeDetected,
    CheckCompleted,
    Event,
    EventBus,
    FetchFailed,
    WatcherState,
    WatcherStateChanged,
)
from watchtower.models import Change, ChangeEvent, ChangeKind


def test_event_bus_publish_and_subscribe() -> None:
    """Test subscribing to events and receiving dispatched objects."""
    bus = EventBus()
    received_checks: list[CheckCompleted] = []

    def on_check(event: CheckCompleted) -> None:
        received_checks.append(event)

    bus.subscribe(CheckCompleted, on_check)

    check_event = CheckCompleted(
        watcher_name="test_watcher",
        duration_seconds=0.15,
        ok=True,
    )
    bus.publish(check_event)

    assert len(received_checks) == 1
    assert received_checks[0].watcher_name == "test_watcher"
    assert received_checks[0].duration_seconds == 0.15
    assert received_checks[0].ok is True
    assert isinstance(received_checks[0], Event)
    assert received_checks[0].timestamp is not None

    # Test unsubscribe
    bus.unsubscribe(CheckCompleted, on_check)
    bus.publish(check_event)
    assert len(received_checks) == 1


def test_event_bus_error_isolation(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that a failing subscriber does not prevent other subscribers from running."""
    bus = EventBus()
    received: list[str] = []

    def failing_handler(event: FetchFailed) -> None:
        raise RuntimeError("Subscriber crashed!")

    def working_handler(event: FetchFailed) -> None:
        received.append(event.error)

    bus.subscribe(FetchFailed, failing_handler)
    bus.subscribe(FetchFailed, working_handler)

    with caplog.at_level(logging.ERROR):
        bus.publish(FetchFailed(watcher_name="w1", error="Network timeout"))

    # Working handler still ran despite the failure
    assert received == ["Network timeout"]
    assert "Unhandled exception in subscriber" in caplog.text


def test_change_detected_and_watcher_state_changed_events() -> None:
    """Test other event dataclasses."""
    now = datetime.now(UTC)
    change = Change(kind=ChangeKind.NEW)
    change_event = ChangeEvent(
        watcher_name="w",
        timestamp=now,
        changes=(change,),
        summary="summary",
    )
    detected = ChangeDetected(watcher_name="w", event=change_event)
    assert detected.event.summary == "summary"
    assert isinstance(detected, Event)

    state_changed = WatcherStateChanged(
        watcher_name="w",
        old_state=WatcherState.ACTIVE,
        new_state=WatcherState.PAUSED,
    )
    assert state_changed.old_state == WatcherState.ACTIVE
    assert state_changed.old_state == "active"
    assert state_changed.new_state == WatcherState.PAUSED
    assert state_changed.new_state == "paused"
    assert isinstance(state_changed, Event)
