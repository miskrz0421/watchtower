"""Tests for the desktop notifier."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from watchtower import (
    Change,
    ChangeEvent,
    ChangeKind,
    Item,
    MissingDependencyError,
    NotifyError,
    list_plugins,
)
from watchtower.notifiers import DesktopNotifier


def _event(*changes: Change) -> ChangeEvent:
    """Build a change event for the tests."""
    return ChangeEvent(
        watcher_name="Cheap flats",
        timestamp=datetime(2026, 11, 21, 10, 0, tzinfo=UTC),
        changes=changes,
        summary="2 change(s) detected",
    )


def test_desktop_plugin_is_registered_by_import() -> None:
    """Importing watchtower registers the desktop plugin without extra work."""
    assert "desktop" in list_plugins()["notifier"]


def test_desktop_notifier_requires_extra(no_desktop_notifier: None) -> None:
    """A missing desktop-notifier package explains how to install it."""
    with pytest.raises(MissingDependencyError, match=r"watchtower\[desktop\]"):
        DesktopNotifier()


def test_injected_backend_skips_optional_import(no_desktop_notifier: None) -> None:
    """A backend passed by tests avoids importing the optional package."""
    backend = Mock()
    notifier = DesktopNotifier(backend=backend)

    notifier.send(_event())

    backend.send.assert_called_once()


def test_send_shows_summary_and_changes() -> None:
    """The title names the watcher and the message describes every change."""
    backend = Mock()
    backend.send.return_value = "notification-id"
    notifier = DesktopNotifier(backend=backend)
    changes = (
        Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat Krowodrza", price=2800.0)),
        Change(
            kind=ChangeKind.CHANGED,
            item=Item(key="2", title="Flat Kazimierz", price=2400.0),
            before=Item(key="2", title="Flat Kazimierz", price=2500.0),
        ),
    )

    notifier.send(_event(*changes))

    backend.send.assert_called_once()
    title, message = backend.send.call_args.args
    assert title == "Cheap flats: 2 change(s) detected"
    assert "New: Flat Krowodrza, 2 800 zł" in message
    assert "Changed: Flat Kazimierz, 2 500 zł → 2 400 zł" in message


def test_send_includes_text_diff() -> None:
    """A text change shows its diff in the notification body."""
    backend = Mock()
    notifier = DesktopNotifier(backend=backend)
    change = Change(kind=ChangeKind.TEXT, diff_text="@@ -1 +1 @@\n-old\n+new\n")

    notifier.send(_event(change))

    message = backend.send.call_args.args[1]
    assert "--- Diff ---" in message
    assert "-old" in message
    assert "+new" in message


def test_send_wraps_backend_errors_in_notify_error() -> None:
    """A backend failure is reported as NotifyError with the original cause."""
    backend = Mock()
    backend.send.side_effect = RuntimeError("no notification daemon")
    notifier = DesktopNotifier(backend=backend)

    with pytest.raises(NotifyError, match="no notification daemon") as caught:
        notifier.send(_event())

    assert isinstance(caught.value.__cause__, RuntimeError)
