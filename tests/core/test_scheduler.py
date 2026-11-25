"""Tests for the Scheduler, driven by a FakeClock."""

from __future__ import annotations

import logging
import queue
import threading
from datetime import UTC, datetime, timedelta

import pytest

from watchtower import (
    Change,
    ChangeDetected,
    ChangeEvent,
    CheckCompleted,
    ConfigError,
    ConfigReloaded,
    EventBus,
    Snapshot,
    SourceError,
    WatcherState,
    WatcherStateChanged,
)
from watchtower.core import (
    CheckNow,
    FakeClock,
    Pause,
    ReloadConfig,
    Resume,
    Scheduler,
    Watcher,
    WatcherStatus,
)
from watchtower.diffs import Differ, TextDiff
from watchtower.notifiers import Notifier
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


class _SwitchableSource(Source):
    """Source whose server a test can take down and bring back."""

    def __init__(self) -> None:
        """Start with the server up."""
        self.down = False

    def fetch(self) -> str:
        """Return a page, or fail with a SourceError while the server is down."""
        if self.down:
            msg = "server down"
            raise SourceError(msg)
        return "page"

    def parse(self, raw: str) -> list[None]:
        """Return no items."""
        return []


class _BuggyDiffer(Differ):
    """Differ with a bug: it raises an exception that is not a WatchtowerError."""

    def diff(self, old: Snapshot | None, new: Snapshot) -> list[Change]:
        """Fail like a programming error would."""
        msg = "bug"
        raise RuntimeError(msg)


class _AlertLog(Notifier):
    """Notifier keeping the events it gets."""

    def __init__(self) -> None:
        """Start with no events."""
        self.events: list[ChangeEvent] = []

    def send(self, event: ChangeEvent) -> None:
        """Remember the event."""
        self.events.append(event)


class _BrokenNotifier(Notifier):
    """Notifier whose channel does not work."""

    def send(self, event: ChangeEvent) -> None:
        """Fail like an unreachable channel would."""
        msg = "channel down"
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
    name: str,
    seconds: float,
    event_bus: EventBus,
    source: Source | None = None,
    notifiers: list[Notifier] | None = None,
) -> Watcher:
    """Return a text watcher checked every `seconds` that publishes on the bus."""
    return Watcher(
        name=name,
        source=source if source is not None else FakeSource(contents=["page"]),
        differ=TextDiff(),
        notifiers=notifiers,
        event_bus=event_bus,
        interval=timedelta(seconds=seconds),
    )


class _StateLog:
    """Keeps the state changes published on the bus, as (old, new) pairs."""

    def __init__(self, event_bus: EventBus) -> None:
        """Subscribe to WatcherStateChanged on the bus."""
        self.changes: list[tuple[WatcherState, WatcherState]] = []
        event_bus.subscribe(WatcherStateChanged, self._record)

    def _record(self, changed: WatcherStateChanged) -> None:
        """Remember the old and new state."""
        self.changes.append((changed.old_state, changed.new_state))


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


def test_failing_watcher_backs_off_with_doubling_waits(
    clock: FakeClock, bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that each failure in a row doubles the wait before the next check."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource()))

    waits = []
    with caplog.at_level(logging.INFO):
        for _ in range(4):
            scheduler.run_pending()
            due = scheduler.next_due()
            assert due is not None
            waits.append((due - clock.now()).total_seconds())
            clock.advance(waits[-1])

    assert waits == [60, 120, 240, 480]
    assert "'broken' failed 4 time(s) in a row; next check in 0:08:00" in caplog.messages


def test_fifth_failure_disables_the_watcher(clock: FakeClock, bus: EventBus) -> None:
    """Test that a watcher failing five times in a row is no longer checked."""
    states = _StateLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource()))

    for _ in range(5):
        scheduler.run_pending()
        clock.advance(3600)

    assert scheduler.next_due() is None
    assert scheduler.run_pending() == 0
    assert states.changes == [
        (WatcherState.ACTIVE, WatcherState.BACKOFF),
        (WatcherState.BACKOFF, WatcherState.DISABLED),
    ]


def _fail_checks(scheduler: Scheduler, clock: FakeClock, count: int) -> None:
    """Run as many checks of a broken watcher, each after its longest wait."""
    for _ in range(count):
        scheduler.run_pending()
        clock.advance(3600)


def test_disabled_watcher_alerts_the_user_once(clock: FakeClock, bus: EventBus) -> None:
    """Test that only the fifth failure sends an alert, also after a failing CheckNow."""
    alerts = _AlertLog()
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource(), [alerts]))

    _fail_checks(scheduler, clock, 4)
    alerts_in_backoff = list(alerts.events)
    disabled_at = clock.now()
    _fail_checks(scheduler, clock, 1)
    scheduler.submit(CheckNow("broken"))
    scheduler.run_pending()

    assert alerts_in_backoff == []
    assert alerts.events == [
        ChangeEvent(
            watcher_name="broken",
            timestamp=disabled_at,
            changes=(),
            summary="disabled after too many failed checks in a row",
        )
    ]


def test_resumed_watcher_alerts_again_when_it_is_disabled_again(
    clock: FakeClock, bus: EventBus
) -> None:
    """Test that every move to Disabled is worth an alert."""
    alerts = _AlertLog()
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource(), [alerts]))

    _fail_checks(scheduler, clock, 5)
    scheduler.submit(Resume("broken"))
    _fail_checks(scheduler, clock, 5)

    assert len(alerts.events) == 2


def test_disabled_alert_is_not_a_detected_change(clock: FakeClock, bus: EventBus) -> None:
    """Test that the alert does not reach the observers of changes, such as the history."""
    changes: list[ChangeDetected] = []
    bus.subscribe(ChangeDetected, changes.append)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource(), [_AlertLog()]))

    _fail_checks(scheduler, clock, 5)

    assert changes == []


def test_broken_notifier_does_not_stop_the_alert_of_the_others(
    clock: FakeClock, bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that a failing notifier is logged and the next one still gets the alert."""
    alerts = _AlertLog()
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("broken", 30, bus, _DownSource(), [_BrokenNotifier(), alerts]))

    _fail_checks(scheduler, clock, 5)

    assert len(alerts.events) == 1
    assert "failed for watcher 'broken'" in caplog.text


def test_disabled_watcher_without_a_bus_still_alerts(clock: FakeClock) -> None:
    """Test that the alert does not depend on an event bus."""
    alerts = _AlertLog()
    scheduler = Scheduler(clock)
    scheduler.add(
        Watcher(name="broken", source=_DownSource(), differ=TextDiff(), notifiers=[alerts])
    )

    _fail_checks(scheduler, clock, 5)

    assert len(alerts.events) == 1


def test_watcher_recovers_after_a_successful_check(clock: FakeClock, bus: EventBus) -> None:
    """Test that a backing-off watcher is active again, at its interval, once it succeeds."""
    states = _StateLog(bus)
    source = _SwitchableSource()
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("flaky", 30, bus, source))

    source.down = True
    scheduler.run_pending()
    clock.advance(60)
    source.down = False
    scheduler.run_pending()

    assert states.changes == [
        (WatcherState.ACTIVE, WatcherState.BACKOFF),
        (WatcherState.BACKOFF, WatcherState.ACTIVE),
    ]
    assert scheduler.next_due() == clock.now() + timedelta(seconds=30)


def test_paused_watcher_is_not_checked(clock: FakeClock, bus: EventBus) -> None:
    """Test that Pause stops the checks and publishes the new state."""
    states = _StateLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))

    scheduler.submit(Pause("a"))

    assert scheduler.run_pending() == 0
    assert scheduler.next_due() is None
    assert states.changes == [(WatcherState.ACTIVE, WatcherState.PAUSED)]


def test_resume_makes_a_paused_watcher_active_and_due_at_once(
    clock: FakeClock, bus: EventBus
) -> None:
    """Test that Resume brings a paused watcher back and checks it on the next run."""
    states = _StateLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.submit(Pause("a"))
    scheduler.run_pending()

    scheduler.submit(Resume("a"))

    assert scheduler.run_pending() == 1
    assert states.changes[-1] == (WatcherState.PAUSED, WatcherState.ACTIVE)


def test_resume_brings_back_a_disabled_watcher(clock: FakeClock, bus: EventBus) -> None:
    """Test that a disabled watcher whose server is back is active after Resume."""
    source = _SwitchableSource()
    source.down = True
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("flaky", 30, bus, source))
    for _ in range(5):
        scheduler.run_pending()
        clock.advance(3600)
    source.down = False

    scheduler.submit(Resume("flaky"))
    scheduler.run_pending()

    assert scheduler.statuses()[0].state is WatcherState.ACTIVE


def test_check_now_checks_a_paused_watcher_once(clock: FakeClock, bus: EventBus) -> None:
    """Test that CheckNow runs a paused watcher, which then stays paused."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.submit(Pause("a"))
    scheduler.run_pending()

    scheduler.submit(CheckNow("a"))

    assert scheduler.run_pending() == 1
    assert checks.names == ["a"]
    assert scheduler.next_due() is None
    assert scheduler.statuses()[0].state is WatcherState.PAUSED


def test_statuses_show_state_interval_and_last_check(clock: FakeClock, bus: EventBus) -> None:
    """Test that statuses describe every watcher in the order they were added."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.add(_watcher("b", 60, bus))
    assert scheduler.statuses()[0].last_check is None

    scheduler.run_pending()
    scheduler.submit(Pause("b"))
    scheduler.run_pending()

    assert scheduler.statuses() == [
        WatcherStatus("a", WatcherState.ACTIVE, timedelta(seconds=30), _START),
        WatcherStatus("b", WatcherState.PAUSED, timedelta(seconds=60), _START),
    ]


@pytest.mark.parametrize("command", [Pause("missing"), Resume("missing"), CheckNow("missing")])
def test_command_for_an_unknown_watcher_is_ignored(
    clock: FakeClock,
    bus: EventBus,
    caplog: pytest.LogCaptureFixture,
    command: Pause | Resume | CheckNow,
) -> None:
    """Test that a command naming no scheduled watcher is logged and changes nothing."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 60, bus))
    scheduler.run_pending()

    scheduler.submit(command)
    with caplog.at_level(logging.WARNING):
        assert scheduler.run_pending() == 0

    assert f"Ignoring {command!r}: no watcher has that name" in caplog.text


def test_commands_can_be_submitted_from_another_thread(clock: FakeClock, bus: EventBus) -> None:
    """Test that a command submitted by another thread is applied by the scheduler's thread."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 60, bus))
    scheduler.run_pending()

    sender = threading.Thread(target=scheduler.submit, args=(CheckNow("a"),))
    sender.start()
    sender.join()

    assert scheduler.run_pending() == 1


def test_reload_replaces_the_watchers(clock: FakeClock, bus: EventBus) -> None:
    """Test that only the new watchers are scheduled, active and checked in the same run."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock, lambda: [_watcher("b", 30, bus), _watcher("c", 60, bus)], bus)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.add(_watcher("b", 60, bus))
    scheduler.submit(Pause("b"))
    scheduler.run_pending()

    scheduler.submit(ReloadConfig())

    assert scheduler.run_pending() == 2
    assert checks.names == ["a", "b", "c"]
    assert scheduler.statuses() == [
        WatcherStatus("b", WatcherState.ACTIVE, timedelta(seconds=30), _START),
        WatcherStatus("c", WatcherState.ACTIVE, timedelta(seconds=60), _START),
    ]


def test_reload_publishes_the_new_statuses(clock: FakeClock, bus: EventBus) -> None:
    """Test that ConfigReloaded carries the new watchers, not checked yet."""
    reloads: list[ConfigReloaded] = []
    bus.subscribe(ConfigReloaded, reloads.append)
    scheduler = Scheduler(clock, lambda: [_watcher("b", 60, bus)], bus)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.run_pending()

    scheduler.submit(ReloadConfig())
    scheduler.run_pending()

    status = WatcherStatus("b", WatcherState.ACTIVE, timedelta(seconds=60), None)
    assert reloads == [ConfigReloaded(statuses=(status,), timestamp=_START)]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ConfigError("bad file"), "the old watchers keep running: bad file"),
        (RuntimeError("bug"), "Unexpected error while reloading the config"),
    ],
)
def test_failed_reload_keeps_the_old_watchers(
    clock: FakeClock,
    bus: EventBus,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    message: str,
) -> None:
    """Test that a failed reload is logged and changes neither the schedule nor the states."""
    reloads: list[ConfigReloaded] = []
    bus.subscribe(ConfigReloaded, reloads.append)

    def fail_to_load() -> list[Watcher]:
        """Fail like a broken config file would."""
        raise error

    scheduler = Scheduler(clock, fail_to_load, bus)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.run_pending()
    statuses = scheduler.statuses()

    scheduler.submit(ReloadConfig())
    with caplog.at_level(logging.ERROR):
        assert scheduler.run_pending() == 0

    assert message in caplog.text
    assert scheduler.statuses() == statuses
    assert scheduler.next_due() == _START + timedelta(seconds=30)
    assert reloads == []


def test_reload_without_a_loader_is_ignored(
    clock: FakeClock, bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that a scheduler whose watchers were added in Python logs and ignores ReloadConfig."""
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))

    scheduler.submit(ReloadConfig())
    with caplog.at_level(logging.WARNING):
        assert scheduler.run_pending() == 1

    assert "Ignoring ReloadConfig" in caplog.text


def test_reload_without_a_bus_replaces_the_watchers(clock: FakeClock, bus: EventBus) -> None:
    """Test that a scheduler without a bus can reload too; it only publishes nothing."""
    scheduler = Scheduler(clock, lambda: [_watcher("b", 30, bus)])

    scheduler.submit(ReloadConfig())
    scheduler.run_pending()

    assert [status.name for status in scheduler.statuses()] == ["b"]


def test_run_forever_without_watchers_waits_for_a_reload(bus: EventBus) -> None:
    """Test that the loop of a scheduler with a loader goes on, so a reload can bring watchers."""
    checks: queue.SimpleQueue[CheckCompleted] = queue.SimpleQueue()
    reloads: queue.SimpleQueue[ConfigReloaded] = queue.SimpleQueue()
    bus.subscribe(CheckCompleted, checks.put)
    bus.subscribe(ConfigReloaded, reloads.put)
    configs = iter([[], [_watcher("a", 3600, bus)]])
    scheduler = Scheduler(load_watchers=lambda: next(configs), event_bus=bus)
    engine = threading.Thread(target=scheduler.run_forever)
    engine.start()

    scheduler.submit(ReloadConfig())
    emptied = reloads.get(timeout=5)
    scheduler.submit(ReloadConfig())
    check = checks.get(timeout=5)
    scheduler.stop()
    engine.join(timeout=5)

    assert emptied.statuses == ()
    assert check.watcher_name == "a"
    assert not engine.is_alive()


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


def test_stop_before_run_forever_makes_it_return_at_once(clock: FakeClock, bus: EventBus) -> None:
    """Test that a stop sent before the loop starts is not lost (the GUI can quit at once)."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))

    scheduler.stop()
    scheduler.run_forever()

    assert checks.names == []


def test_run_forever_can_run_again_after_a_stop(clock: FakeClock, bus: EventBus) -> None:
    """Test that a stop ends only the run it was meant for."""
    checks = _CheckLog(bus)
    scheduler = Scheduler(clock)
    scheduler.add(_watcher("a", 30, bus))
    scheduler.stop()
    scheduler.run_forever()

    def stop_after_the_check(check: CheckCompleted) -> None:
        """Stop the second run once it has checked the watcher."""
        scheduler.stop()

    bus.subscribe(CheckCompleted, stop_after_the_check)
    scheduler.run_forever()

    assert checks.names == ["a"]


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


def test_run_forever_with_every_watcher_paused_waits_for_a_command(bus: EventBus) -> None:
    """Test that the loop waits without a time limit until a command brings a watcher back."""
    states: queue.SimpleQueue[WatcherStateChanged] = queue.SimpleQueue()
    checks: queue.SimpleQueue[CheckCompleted] = queue.SimpleQueue()
    bus.subscribe(WatcherStateChanged, states.put)
    bus.subscribe(CheckCompleted, checks.put)
    scheduler = Scheduler()
    scheduler.add(_watcher("a", 3600, bus))
    scheduler.submit(Pause("a"))
    engine = threading.Thread(target=scheduler.run_forever)
    engine.start()

    states.get(timeout=5)
    scheduler.submit(Resume("a"))
    check = checks.get(timeout=5)
    scheduler.stop()
    engine.join(timeout=5)

    assert check.watcher_name == "a"


def test_default_clock_is_the_system_clock() -> None:
    """Test that a scheduler without a clock uses the real time."""
    before = datetime.now(UTC)
    scheduler = Scheduler()
    scheduler.add(_watcher("a", 30, EventBus()))
    due = scheduler.next_due()
    assert due is not None
    assert before <= due <= datetime.now(UTC)
