"""Tests for the Discord notifier."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest

from watchtower import (
    Change,
    ChangeEvent,
    ChangeKind,
    Item,
    NotifyError,
    create_notifier,
    list_plugins,
)
from watchtower.core import Watcher
from watchtower.diffs import TextDiff
from watchtower.notifiers import DiscordNotifier
from watchtower.sources import FakeSource

WEBHOOK_URL = "https://discord.com/api/webhooks/1234/top-secret-token"


def _event(*changes: Change) -> ChangeEvent:
    """Build a change event for the tests."""
    return ChangeEvent(
        watcher_name="Cheap flats",
        timestamp=datetime(2026, 11, 21, 10, 0, tzinfo=UTC),
        changes=changes,
        summary="2 change(s) detected",
    )


def _item_changes() -> tuple[Change, ...]:
    """Build one new item and one changed item."""
    return (
        Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat Krowodrza", price=2800.0)),
        Change(
            kind=ChangeKind.CHANGED,
            item=Item(key="2", title="Flat Kazimierz", price=2400.0),
            before=Item(key="2", title="Flat Kazimierz", price=2500.0),
        ),
    )


def _recording_transport(
    recorded: dict[str, httpx.Request], response: httpx.Response | None = None
) -> httpx.MockTransport:
    """Record the outgoing request and reply with a successful webhook response."""

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["request"] = request
        return response if response is not None else httpx.Response(204)

    return httpx.MockTransport(handler)


def test_discord_plugin_is_registered_by_import() -> None:
    """Importing watchtower makes the notifier creatable by its plugin name."""
    assert "discord" in list_plugins()["notifier"]
    assert isinstance(create_notifier("discord", webhook_url=WEBHOOK_URL), DiscordNotifier)


def test_send_posts_summary_and_changes() -> None:
    """The webhook receives a POST with the same change lines as other notifiers."""
    recorded: dict[str, httpx.Request] = {}
    notifier = DiscordNotifier(WEBHOOK_URL, transport=_recording_transport(recorded))

    notifier.send(_event(*_item_changes()))

    request = recorded["request"]
    assert request.method == "POST"
    assert str(request.url) == WEBHOOK_URL
    assert request.headers["user-agent"] == "Watchtower/0.1"
    assert json.loads(request.content)["content"] == (
        "**Cheap flats: 2 change(s) detected**\n"
        "New: Flat Krowodrza, 2 800 zł\n"
        "Changed: Flat Kazimierz, 2 500 zł → 2 400 zł"
    )


def test_send_includes_text_diff() -> None:
    """A text change includes its diff in the message body."""
    recorded: dict[str, httpx.Request] = {}
    notifier = DiscordNotifier(WEBHOOK_URL, transport=_recording_transport(recorded))
    change = Change(kind=ChangeKind.TEXT, diff_text="@@ -1 +1 @@\n-old\n+new\n")

    notifier.send(_event(change))

    content = json.loads(recorded["request"].content)["content"]
    assert "--- Diff ---" in content
    assert "-old" in content
    assert "+new" in content


def test_send_uses_configured_timeout() -> None:
    """The timeout passed to the constructor is the one used for the request."""
    recorded: dict[str, httpx.Request] = {}
    notifier = DiscordNotifier(WEBHOOK_URL, timeout=2.5, transport=_recording_transport(recorded))

    notifier.send(_event())

    assert recorded["request"].extensions["timeout"] == {
        "connect": 2.5,
        "read": 2.5,
        "write": 2.5,
        "pool": 2.5,
    }


def test_http_error_raises_notify_error_without_leaking_the_webhook() -> None:
    """A rejected webhook reports only the status, with the failing request suppressed."""
    transport = httpx.MockTransport(lambda request: httpx.Response(400, text="Bad Request"))
    notifier = DiscordNotifier(WEBHOOK_URL, transport=transport)

    with pytest.raises(NotifyError, match="Discord webhook returned HTTP 400") as caught:
        notifier.send(_event())

    assert caught.value.__cause__ is None
    assert str(caught.value) == "Discord webhook returned HTTP 400"


def test_connection_error_raises_notify_error_without_leaking_the_webhook() -> None:
    """A network failure reports only its exception class, with the cause suppressed."""

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    notifier = DiscordNotifier(WEBHOOK_URL, transport=httpx.MockTransport(fail))

    with pytest.raises(NotifyError, match="Discord webhook failed: ConnectError") as caught:
        notifier.send(_event())

    assert caught.value.__cause__ is None
    assert str(caught.value) == "Discord webhook failed: ConnectError"


def test_watcher_logs_webhook_failure_without_the_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The watcher's error log contains the safe message but never the webhook token."""
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    watcher = Watcher(
        name="cheap flats",
        source=FakeSource(contents=["version 1\n", "version 2\n"]),
        differ=TextDiff(),
        notifiers=[DiscordNotifier(WEBHOOK_URL, transport=transport)],
    )
    watcher.check_once()  # first check establishes the baseline

    with caplog.at_level(logging.ERROR, logger="watchtower.core._watcher"):
        watcher.check_once()  # second check detects a change and notifies

    assert "Discord webhook returned HTTP 500" in caplog.text
    assert "top-secret-token" not in caplog.text


def test_send_truncates_message_to_discord_limit() -> None:
    """An oversized diff is cut to Discord's 2000-character content limit."""
    recorded: dict[str, httpx.Request] = {}
    notifier = DiscordNotifier(WEBHOOK_URL, transport=_recording_transport(recorded))
    change = Change(kind=ChangeKind.TEXT, diff_text="x" * 5000)

    notifier.send(_event(change))

    content = json.loads(recorded["request"].content)["content"]
    assert len(content) == 2000
    assert content.endswith("…")
