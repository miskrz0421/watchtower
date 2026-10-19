"""Tests for the Watcher pipeline."""

from __future__ import annotations

import io

import pytest

from watchtower.core.watcher import Watcher
from watchtower.diffs.text import TextDiff
from watchtower.errors import SourceError
from watchtower.events import ChangeDetected, CheckCompleted, EventBus, FetchFailed
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource


class FailingSource(Source):
    """Source that simulates runtime failure."""

    def fetch(self) -> str:
        msg = "Fetch timeout error"
        raise SourceError(msg)

    def parse(self, raw: str) -> list[None]:
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
