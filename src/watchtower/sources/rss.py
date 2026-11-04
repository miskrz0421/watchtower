"""RSSSource for monitoring RSS and Atom feeds."""

from __future__ import annotations

from collections.abc import Iterable

from watchtower.models import Item
from watchtower.registry import register_source
from watchtower.sources.http import HttpSource


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
        """
        raise NotImplementedError
