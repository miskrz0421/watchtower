"""Tests for the EngineThread."""

from __future__ import annotations

import threading

import pytest
from pytestqt.qtbot import QtBot

from watchtower import CheckCompleted, EventBus
from watchtower.core import Scheduler
from watchtower.gui import EngineThread

pytestmark = pytest.mark.gui


class _CheckThreads:
    """Keeps the thread each check ran in, from the bus."""

    def __init__(self, event_bus: EventBus) -> None:
        """Subscribe to CheckCompleted on the bus."""
        self.threads: list[threading.Thread] = []
        event_bus.subscribe(CheckCompleted, self._record)

    def _record(self, check: CheckCompleted) -> None:
        """Remember the thread that published the check."""
        self.threads.append(threading.current_thread())


def test_checks_run_outside_the_gui_thread(
    qtbot: QtBot, bus: EventBus, hourly_scheduler: Scheduler
) -> None:
    """Test that the scheduler checks its watchers in the engine thread."""
    checks = _CheckThreads(bus)
    engine = EngineThread(hourly_scheduler)

    engine.start()
    qtbot.waitUntil(lambda: len(checks.threads) == 1)
    engine.stop()

    assert checks.threads[0] is not threading.main_thread()


def test_stop_ends_the_thread_without_waiting_for_the_next_check(
    qtbot: QtBot, bus: EventBus, hourly_scheduler: Scheduler
) -> None:
    """Test that stop returns at once although the next check is an hour away."""
    checks = _CheckThreads(bus)
    engine = EngineThread(hourly_scheduler)
    engine.start()
    qtbot.waitUntil(lambda: len(checks.threads) == 1)

    engine.stop()

    assert engine.isFinished()


def test_stop_right_after_start_ends_the_thread(hourly_scheduler: Scheduler) -> None:
    """Test that quitting as soon as the app opens does not leave the engine running."""
    engine = EngineThread(hourly_scheduler)

    engine.start()
    engine.stop()

    assert engine.isFinished()
