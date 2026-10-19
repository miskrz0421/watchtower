"""ConsoleNotifier implementation printing formatted changes to stdout."""

from __future__ import annotations

import sys
from typing import TextIO

from watchtower.models import ChangeEvent, ChangeKind
from watchtower.notifiers.base import Notifier
from watchtower.registry import register_notifier


@register_notifier("console")
class ConsoleNotifier(Notifier):
    """Notifier writing formatted event summaries and diffs to a text stream."""

    def __init__(self, stream: TextIO | None = None) -> None:
        """Initialize ConsoleNotifier with an optional output stream.

        Args:
            stream: Text stream to write to (defaults to sys.stdout).
        """
        self.stream = stream if stream is not None else sys.stdout

    def send(self, event: ChangeEvent) -> None:
        """Format and print the event to the configured stream.

        Args:
            event: ChangeEvent to output.
        """
        time_str = event.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        self.stream.write(f"\n[{time_str}] [{event.watcher_name}] {event.summary}\n")

        for change in event.changes:
            if change.kind == ChangeKind.TEXT and change.diff_text:
                self.stream.write("--- Diff ---\n")
                self.stream.write(change.diff_text)
                if not change.diff_text.endswith("\n"):
                    self.stream.write("\n")
            elif change.item is not None:
                self.stream.write(f"- [{change.kind.value.upper()}] {change.item}\n")
            else:
                self.stream.write(f"- [{change.kind.value.upper()}]\n")
        self.stream.flush()
