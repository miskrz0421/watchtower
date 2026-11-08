"""Tests for Notifiers and ConsoleNotifier."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

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


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (
            Change(
                kind=ChangeKind.NEW,
                item=Item(key="1", title="Flat Krowodrza", price=2800.0),
            ),
            "New: Flat Krowodrza, 2800 zł",
        ),
        (
            Change(
                kind=ChangeKind.REMOVED,
                item=Item(key="1", title="Flat Kazimierz", price=2400.5),
            ),
            "Removed: Flat Kazimierz, 2400.5 zł",
        ),
        (
            Change(
                kind=ChangeKind.CHANGED,
                item=Item(key="1", title="Flat Stare Miasto", price=3200.0),
                before=Item(key="1", title="Flat Stare Miasto", price=3500.0),
            ),
            "Changed: Flat Stare Miasto, 3200 zł",
        ),
        (
            Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat without price")),
            "New: Flat without price",
        ),
    ],
)
def test_console_notifier_formats_item_changes(change: Change, expected: str) -> None:
    """Test that item changes print as readable lines."""
    stream = io.StringIO()
    notifier = ConsoleNotifier(stream=stream)
    event = ChangeEvent(
        watcher_name="flat_watcher",
        timestamp=datetime.now(UTC),
        changes=(change,),
        summary="1 change",
    )

    notifier.send(event)
    output = stream.getvalue()

    assert expected in output
    assert "Item(" not in output


def test_registry_creates_console_notifier() -> None:
    """Test creating ConsoleNotifier through registry."""
    notifier = create_notifier("console")
    assert isinstance(notifier, ConsoleNotifier)
