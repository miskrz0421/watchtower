"""RSSSource for monitoring RSS and Atom feeds."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol, cast

import feedparser

from watchtower.errors import ParseError
from watchtower.models import Item
from watchtower.registry import register_source
from watchtower.sources.http import HttpSource
from watchtower.sources.parsing import parse_price


class _Feed(Protocol):
    """The part of feedparser's result that RSSSource uses."""

    entries: Sequence[Mapping[str, object]]

    def get(self, key: str) -> object:
        """Return a top-level field, or None when feedparser did not set it."""
        ...


@register_source("rss")
class RSSSource(HttpSource):
    """Source producing one Item per feed entry."""

    def parse(self, raw: str) -> Iterable[Item]:
        """Parse a feed with feedparser into Items.

        Each Item's key is the entry's `id`, falling back to its `link`.

        Args:
            raw: Feed XML returned by `fetch()`.

        Returns:
            An iterable of Items, one per feed entry.

        Raises:
            ParseError: If the text is not an RSS or Atom feed, or an entry
                has no id or link, or no title.
        """
        feed = cast(_Feed, feedparser.parse(raw))
        if not feed.entries and not feed.get("version"):
            # feedparser does not raise on an error page; without this check an
            # outage would look like every Item was removed.
            msg = "Response is not an RSS or Atom feed"
            raise ParseError(msg)
        return [_to_item(entry, position) for position, entry in enumerate(feed.entries, start=1)]


def _to_item(entry: Mapping[str, object], position: int) -> Item:
    """Convert one feed entry to an Item, validating the required fields."""
    key = _non_empty_string(entry.get("id")) or _non_empty_string(entry.get("link"))
    if key is None:
        msg = f"Feed entry {position} has no id or link"
        raise ParseError(msg)

    title = _non_empty_string(entry.get("title"))
    if title is None:
        msg = f"Feed entry {position} ({key!r}) has no title"
        raise ParseError(msg)

    text = (
        _non_empty_string(entry.get("summary")) or _non_empty_string(entry.get("description")) or ""
    )
    price = parse_price(text)
    if price is None:
        price = parse_price(_non_empty_string(entry.get("price")) or "")
    return Item(
        key=key,
        title=title,
        url=_non_empty_string(entry.get("link")),
        price=price,
        text=text,
        published=_published(entry, position),
    )


def _non_empty_string(value: object) -> str | None:
    """Return a non-blank string, or None when the value is missing or blank."""
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _published(entry: Mapping[str, object], position: int) -> datetime | None:
    """Return the entry's publication time in UTC, if the feed has one."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    if not isinstance(parsed, (tuple, list)) or len(parsed) < 6:
        msg = f"Feed entry {position} has an invalid publication date"
        raise ParseError(msg)
    try:
        year, month, day, hour, minute, second = (int(part) for part in parsed[:6])
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except (TypeError, ValueError) as err:
        msg = f"Feed entry {position} has an invalid publication date: {err}"
        raise ParseError(msg) from err
