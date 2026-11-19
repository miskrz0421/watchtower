"""Fixtures for the GUI tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from watchtower import EventBus
from watchtower.core import Scheduler, Watcher
from watchtower.diffs import TextDiff
from watchtower.sources import FakeSource


@pytest.fixture
def bus() -> EventBus:
    """Return an empty event bus."""
    return EventBus()


@pytest.fixture
def hourly_scheduler(bus: EventBus) -> Scheduler:
    """Return a scheduler with one watcher, checked every hour, publishing on the bus."""
    scheduler = Scheduler()
    scheduler.add(
        Watcher(
            name="hourly",
            source=FakeSource(contents=["page"]),
            differ=TextDiff(),
            event_bus=bus,
            interval=timedelta(hours=1),
        )
    )
    return scheduler
