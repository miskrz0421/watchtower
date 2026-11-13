"""ConsoleNotifier implementation printing formatted changes to stdout."""

from __future__ import annotations

import sys
from datetime import tzinfo
from typing import TextIO

from watchtower.models import Change, ChangeEvent, ChangeKind, Item
from watchtower.notifiers.base import Notifier
from watchtower.registry import register_notifier


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
            self._stream.write(f"{_change_text(change)}\n")
        self._stream.flush()


def _change_text(change: Change) -> str:
    """Describe one change: a text diff, an item line, or just the kind of change.

    Args:
        change: Change to describe.

    Returns:
        The text to print, without a trailing newline.
    """
    if change.kind == ChangeKind.TEXT and change.diff_text:
        text = f"--- Diff ---\n{change.diff_text.removesuffix('\n')}"
    elif change.item is not None:
        text = _item_line(change.kind, change.item, change.before)
    else:
        text = change.kind.value.capitalize()
    return text


def _item_line(kind: ChangeKind, item: Item, before: Item | None) -> str:
    """Describe an item change in one line, e.g. 'Changed: Flat, 2 800 zł → 2 600 zł'.

    Args:
        kind: Kind of the change.
        item: Item after the change.
        before: Item before the change, for a changed item.

    Returns:
        The line to print.
    """
    line = f"{kind.value.capitalize()}: {item.title}"
    if before is not None and before.price != item.price:
        line += f", {_price(before.price)} → {_price(item.price)}"
    elif item.price is not None:
        line += f", {_price(item.price)}"
    if before is not None and before.title != item.title:
        line += f" (was: {before.title})"
    return line


def _price(price: float | None) -> str:
    """Format a price the Polish way, e.g. '2 800 zł' or '2 400,50 zł'.

    Args:
        price: Price to format, or None.

    Returns:
        The formatted price, or 'no price' for None.
    """
    if price is None:
        return "no price"
    if price.is_integer():
        return f"{int(price):,} zł".replace(",", " ")
    grouped = f"{price:,.2f}"  # '2,400.50'
    return grouped.replace(",", " ").replace(".", ",") + " zł"
