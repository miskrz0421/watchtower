"""Tests for the LoggingObserver."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from watchtower import (
    Change,
    ChangeDetected,
    ChangeEvent,
    ChangeKind,
    CheckCompleted,
    EventBus,
    FetchFailed,
    WatcherState,
    WatcherStateChanged,
)
from watchtower.core import LoggingObserver


@pytest.fixture
def bus() -> EventBus:
    """Return an event bus with a LoggingObserver attached."""
    event_bus = EventBus()
    LoggingObserver().attach(event_bus)
    return event_bus


def test_successful_check_is_logged_at_info(
    bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that a successful check is logged with its duration."""
    with caplog.at_level(logging.INFO):
        bus.publish(CheckCompleted(watcher_name="Flats", duration_seconds=0.25, ok=True))

    assert caplog.record_tuples == [
        ("watchtower.core._logging_observer", logging.INFO, "Checked 'Flats' in 0.25 s: ok")
    ]


def test_failed_check_is_logged_at_warning(bus: EventBus, caplog: pytest.LogCaptureFixture) -> None:
    """Test that a failed check is logged with its error, once."""
    with caplog.at_level(logging.INFO):
        bus.publish(FetchFailed(watcher_name="Flats", error="server down"))
        bus.publish(
            CheckCompleted(
                watcher_name="Flats", duration_seconds=0.5, ok=False, error="server down"
            )
        )

    assert caplog.record_tuples == [
        (
            "watchtower.core._logging_observer",
            logging.WARNING,
            "Checked 'Flats' in 0.50 s: failed: server down",
        )
    ]


def test_detected_change_is_logged_with_its_summary(
    bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that reported changes are logged with the event's summary."""
    event = ChangeEvent(
        watcher_name="Flats",
        timestamp=datetime(2026, 11, 16, 12, 0, tzinfo=UTC),
        changes=(Change(kind=ChangeKind.NEW),),
        summary="1 change(s) detected",
    )
    with caplog.at_level(logging.INFO):
        bus.publish(ChangeDetected(watcher_name="Flats", event=event))

    assert caplog.messages == ["'Flats': 1 change(s) detected"]


@pytest.mark.parametrize(
    ("new_state", "level"),
    [
        (WatcherState.BACKOFF, logging.WARNING),
        (WatcherState.DISABLED, logging.WARNING),
        (WatcherState.PAUSED, logging.INFO),
    ],
)
def test_state_change_is_logged_at_warning_only_when_failing(
    bus: EventBus, caplog: pytest.LogCaptureFixture, new_state: WatcherState, level: int
) -> None:
    """Test that backoff and disabled are warnings and other states are info."""
    with caplog.at_level(logging.INFO):
        bus.publish(
            WatcherStateChanged(
                watcher_name="Flats", old_state=WatcherState.ACTIVE, new_state=new_state
            )
        )

    assert caplog.record_tuples == [
        ("watchtower.core._logging_observer", level, f"'Flats' is now {new_state} (was active)")
    ]
