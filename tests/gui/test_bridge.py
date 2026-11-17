"""Tests for the EngineBridge."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytestqt.qtbot import QtBot

from watchtower import (
    ChangeDetected,
    ChangeEvent,
    CheckCompleted,
    Event,
    EventBus,
    FetchFailed,
    WatcherState,
    WatcherStateChanged,
)
from watchtower.gui import EngineBridge

pytestmark = pytest.mark.gui

_EMPTY_EVENT = ChangeEvent(
    watcher_name="a", timestamp=datetime(2026, 11, 17, tzinfo=UTC), changes=(), summary=""
)

_SIGNAL_FOR_EVENT = [
    ("check_completed", CheckCompleted(watcher_name="a", duration_seconds=0.1, ok=True)),
    ("change_detected", ChangeDetected(watcher_name="a", event=_EMPTY_EVENT)),
    ("fetch_failed", FetchFailed(watcher_name="a", error="server down")),
    (
        "state_changed",
        WatcherStateChanged(
            watcher_name="a", old_state=WatcherState.ACTIVE, new_state=WatcherState.BACKOFF
        ),
    ),
]


@pytest.mark.parametrize(
    ("signal_name", "event"), _SIGNAL_FOR_EVENT, ids=[name for name, _ in _SIGNAL_FOR_EVENT]
)
def test_bus_event_is_emitted_as_a_signal(qtbot: QtBot, signal_name: str, event: Event) -> None:
    """Test that each event published on the bus comes out as its own signal."""
    bus = EventBus()
    bridge = EngineBridge()
    bridge.attach(bus)

    with qtbot.waitSignal(getattr(bridge, signal_name)) as emitted:
        bus.publish(event)

    assert emitted.args == [event]
