"""Tests for the Scheduler, driven by a FakeClock."""

from __future__ import annotations

import logging
import queue
import threading
from datetime import UTC, datetime, timedelta

import pytest

from watchtower import Change, CheckCompleted, EventBus, Snapshot, SourceError
from watchtower.core import CheckNow, FakeClock, Scheduler, Watcher
from watchtower.diffs import Differ, TextDiff
from watchtower.sources import FakeSource, Source

_START = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


class _DownSource(Source):
    """Source whose server cannot be reached."""

    def fetch(self) -> str:
        """Fail with a SourceError."""
        msg = "server down"
        raise SourceError(msg)

    def parse(self, raw: str) -> list[None]:
        """Return no items; never reached."""
        return []


class _BuggyDiffer(Differ):
    """Differ with a bug: it raises an exception that is not a WatchtowerError."""

    def diff(self, old: Snapshot | None, new: Snapshot) -> list[Change]:
        """Fail like a programming error would."""
        msg = "bug"
        raise RuntimeError(msg)


class _CheckLog:
    """Keeps the names of checked watchers, in order, from the bus."""

    def __init__(self, event_bus: EventBus) -> None:
        """Subscribe to CheckCompleted on the bus."""
        self.names: list[str] = []
        event_bus.subscribe(CheckCompleted, self._record)

    def _record(self, check: CheckCompleted) -> None:
        """Remember which watcher was checked."""
        self.names.append(check.watcher_name)


def _watcher(
    name: str, seconds: float, event_bus: EventBus, source: Source | None = None
) -> Watcher:
    """Return a text watcher checked every `seconds` that publishes on the bus."""
    return Watcher(
        name=name,
        source=source if source is not None else FakeSource(contents=["page"]),
        differ=TextDiff(),
        event_bus=event_bus,
        interval=timedelta(seconds=seconds),
    )


@pytest.fixture
def clock() -> FakeClock:
    """Return a FakeClock starting at a fixed time."""
    return FakeClock(_START)


@pytest.fixture
def bus() -> EventBus:
    """Return an empty event bus."""
    return EventBus()


def test_next_due_is_none_without_watchers(clock: FakeClock) -> None:
    """Test that an empty scheduler has nothing due."""
    assert Scheduler(clock).next_due() is None


def test_added_watcher_is_due_at_once(clock: FakeClock, bus: EventBus) -> None:
    """Test that a new watcher is checked on the first run_pending."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    assert scheduler.next_due() == _START
    assert scheduler.run_pending() == 1


def test_watcher_is_due_again_after_its_interval(clock: FakeClock, bus: EventBus) -> None:
    """Test that a checked watcher waits exactly one interval for its next check."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.run_pending()

    assert scheduler.next_due() == _START + timedelta(seconds=30)
    clock.advance(29)
    assert scheduler.run_pending() == 0
    clock.advance(1)
    assert scheduler.run_pending() == 1


def test_only_due_watchers_are_checked(clock: FakeClock, bus: EventBus) -> None:
    """Test that watchers with different intervals run on their own schedules."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("fast", 30, bus))
    scheduler.add(_watcher("slow", 60, bus))

    scheduler.run_pending()
    clock.advance(30)
    scheduler.run_pending()
    clock.advance(30)
    scheduler.run_pending()

    assert checks.names == ["fast", "slow", "fast", "fast", "slow"]


def test_adding_a_name_twice_is_refused(clock: FakeClock, bus: EventBus) -> None:
    """Test that two watchers with the same name cannot be scheduled."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    with pytest.raises(ValueError, match="already scheduled"):
        scheduler.add(_watcher("a", 60, bus))


def test_failing_watcher_does_not_stop_the_others(clock: FakeClock, bus: EventBus) -> None:
    """Test that a failed check is retried after its interval and the rest still run."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource()))
    scheduler.add(_watcher("fine", 30, bus))

    assert scheduler.run_pending() == 2
    assert scheduler.next_due() == _START + timedelta(seconds=30)
    assert checks.names == ["broken", "fine"]


def test_unexpected_error_is_logged_with_traceback(
    clock: FakeClock, bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that an exception that is not a WatchtowerError is logged as a bug."""
    scheduler = Scheduler(clock)
    buggy = Watcher(name="buggy", source=FakeSource(), differ=_BuggyDiffer(), event_bus=bus)
    scheduler.add(buggy)

    with caplog.at_level(logging.ERROR):
        assert scheduler.run_pending() == 1

    assert "Unexpected error in watcher 'buggy'" in caplog.text
    assert "RuntimeError: bug" in caplog.text


def test_check_now_runs_a_watcher_before_its_interval(clock: FakeClock, bus: EventBus) -> None:
    """Test that a CheckNow command makes a waiting watcher due on the next run."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 60, bus))
    scheduler.run_pending()
    clock.advance(10)

    scheduler.submit(CheckNow("a"))

    assert scheduler.run_pending() == 1
    assert checks.names == ["a", "a"]
    assert scheduler.next_due() == _START + timedelta(seconds=70)


def test_check_now_for_an_unknown_watcher_is_ignored(
    clock: FakeClock, bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that a command naming no scheduled watcher is logged and changes nothing."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 60, bus))
    scheduler.run_pending()

    scheduler.submit(CheckNow("missing"))
    with caplog.at_level(logging.WARNING):
        assert scheduler.run_pending() == 0

    assert "Cannot check 'missing' now" in caplog.text


def test_commands_can_be_submitted_from_another_thread(clock: FakeClock, bus: EventBus) -> None:
    """Test that a command submitted by another thread is applied by the scheduler's thread."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 60, bus))
    scheduler.run_pending()

    sender = threading.Thread(target=scheduler.submit, args=(CheckNow("a"),))
    sender.start()
    sender.join()

    assert scheduler.run_pending() == 1


def test_run_forever_sleeps_until_each_due_check(clock: FakeClock, bus: EventBus) -> None:
    """Test that run_forever checks on time and returns after stop is called."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("fast", 30, bus))
    scheduler.add(_watcher("slow", 60, bus))

    def stop_after_five_checks(check: CheckCompleted) -> None:
        """Stop the scheduler once five checks have run."""
        if len(checks.names) == 5:
            scheduler.stop()

    bus.subscribe(CheckCompleted, stop_after_five_checks)
    scheduler.run_forever()

    assert checks.names == ["fast", "slow", "fast", "fast", "slow"]
    assert clock.now() == _START + timedelta(seconds=60)


def test_run_forever_without_watchers_returns(clock: FakeClock) -> None:
    """Test that run_forever does not loop when there is nothing to run."""
    Scheduler(clock).run_forever()
    assert clock.now() == _START


def test_stop_from_another_thread_ends_the_wait(bus: EventBus) -> None:
    """Test that stop ends a long wait at once instead of after the next check."""
    checks: queue.SimpleQueue[CheckCompleted] = queue.SimpleQueue()
    bus.subscribe(CheckCompleted, checks.put)
    scheduler = Scheduler()
    scheduler.add(_watcher("hourly", 3600, bus))
    engine = threading.Thread(target=scheduler.run_forever)
    engine.start()

    checks.get(timeout=5)
    scheduler.stop()
    engine.join(timeout=5)

    assert not engine.is_alive()


def test_command_from_another_thread_ends_the_wait(bus: EventBus) -> None:
    """Test that a submitted command is applied at once, not after the interval."""
    checks: queue.SimpleQueue[CheckCompleted] = queue.SimpleQueue()
    bus.subscribe(CheckCompleted, checks.put)
    scheduler = Scheduler()
    scheduler.add(_watcher("hourly", 3600, bus))
    engine = threading.Thread(target=scheduler.run_forever)
    engine.start()

    checks.get(timeout=5)
    scheduler.submit(CheckNow("hourly"))
    second = checks.get(timeout=5)
    scheduler.stop()
    engine.join(timeout=5)

    assert second.watcher_name == "hourly"


def test_default_clock_is_the_system_clock() -> None:
    """Test that a scheduler without a clock uses the real time."""
    before = datetime.now(UTC)
    scheduler = Scheduler()
    scheduler.add(_watcher("a", 30, EventBus()))
    due = scheduler.next_due()
    assert due is not None
    assert before <= due <= datetime.now(UTC)
