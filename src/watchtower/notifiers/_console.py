"""ConsoleNotifier implementation printing formatted changes to stdout."""

from __future__ import annotations

import sys
from datetime import tzinfo
from typing import TextIO

from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier
from watchtower.notifiers._format import change_text


@register_notifier("console")
class ConsoleNotifier(Notifier):
    """Notifier writing formatted event summaries and diffs to a text stream."""

    def __init__(self, stream: TextIO | None = None, tz: tzinfo | None = None) -> None:
        """Initialize ConsoleNotifier with an optional output stream.

        Args:
            stream: Text stream to write to (defaults to sys.stdout).
            tz: Time zone used to display event times; None means the
                computer's local time zone. Events are stored in UTC.
        """
        self._stream = stream if stream is not None else sys.stdout
        self._tz = tz

    def send(self, event: ChangeEvent) -> None:
        """Format and print the event to the configured stream.

        Args:
            event: ChangeEvent to output.
        """
        time_str = event.timestamp.astimezone(self._tz).strftime("%Y-%m-%d %H:%M:%S")
        self._stream.write(f"\n[{time_str}] [{event.watcher_name}] {event.summary}\n")

        for change in event.changes:
            self._stream.write(f"{change_text(change)}\n")
        self._stream.flush()
