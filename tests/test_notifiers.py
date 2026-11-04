"""Tests for Notifiers and ConsoleNotifier."""

from __future__ import annotations

import io
from datetime import UTC, datetime

from watchtower.models import Change, ChangeEvent, ChangeKind, Item
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.registry import create_notifier


def test_console_notifier_outputs_text_diff() -> None:
    """Test ConsoleNotifier formatting text diff changes."""
    stream = io.StringIO()
    notifier = ConsoleNotifier(stream=stream)

    change = Change(kind=ChangeKind.TEXT, diff_text="@@ -1 +1 @@\n-old\n+new\n")
    event = ChangeEvent(
        watcher_name="doc_watcher",
        timestamp=datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC),
        changes=(change,),
        summary="Document changed",
    )

    notifier.send(event)
    output = stream.getvalue()

    assert "[doc_watcher]" in output
    assert "Document changed" in output
    assert "--- Diff ---" in output
    assert "-old" in output
    assert "+new" in output


def test_console_notifier_outputs_item_change() -> None:
    """Test ConsoleNotifier formatting item changes."""
    stream = io.StringIO()
    notifier = ConsoleNotifier(stream=stream)

    item = Item(key="k1", title="Flat in center", price=3000.0)
    change = Change(kind=ChangeKind.NEW, item=item)
    event = ChangeEvent(
        watcher_name="flat_watcher",
        timestamp=datetime.now(UTC),
        changes=(change,),
        summary="1 new flat",
    )

    notifier.send(event)
    output = stream.getvalue()

    assert "[NEW]" in output
    assert "Flat in center" in output


def test_registry_creates_console_notifier() -> None:
    """Test creating ConsoleNotifier through registry."""
    notifier = create_notifier("console")
    assert isinstance(notifier, ConsoleNotifier)
