"""Built-in filters for the most common rules."""

from __future__ import annotations

import re

from watchtower.filters.base import Filter
from watchtower.models import Change, ChangeKind
from watchtower.registry import register_filter


@register_filter("new_items")
class NewItems(Filter):
    """Accepts only changes that add a new item."""

    def matches(self, change: Change) -> bool:
        """Return whether the change is a new item.

        Args:
            change: The change to evaluate.

        Returns:
            True if the kind of the change is NEW.
        """
        return change.kind == ChangeKind.NEW


@register_filter("kind_is")
class KindIs(Filter):
    """Accepts changes changes of one kind."""

    def __init__(self, kind: str) -> None:
        """Initialize KindIs.

        Args:
            kind: The kind of change to keep.
        """
        self._kind = ChangeKind(kind)

    def matches(self, change: Change) -> bool:
        """Return whether the change has the configured kind.

        Args:
            change: The change to evaluate.

        Returns:
            True if the change's kind matches; False otherwise.
        """
        return change.kind == self._kind


@register_filter("price_below")
class PriceBelow(Filter):
    """Accepts changes whose item costs less than a limit."""

    def __init__(self, limit: float) -> None:
        """Initialize PriceBelow.

        Args:
            limit: Price the item must be below.
        """
        self._limit = limit

    def matches(self, change: Change) -> bool:
        """Return whether the item's price is below the limit.

        Args:
            change: The change to evaluate.

        Returns:
            True if the item has a price below the limit; False without a price.
        """
        item = change.item
        return item is not None and item.price is not None and item.price < self._limit


@register_filter("price_above")
class PriceAbove(Filter):
    """Accepts changes whose item costs more than a limit."""

    def __init__(self, limit: float) -> None:
        """Initialize PriceAbove.

        Args:
            limit: Price the item must be above.
        """
        self._limit = limit

    def matches(self, change: Change) -> bool:
        """Return whether the item's price is above the limit.

        Args:
            change: The change to evaluate.

        Returns:
            True if the item has a price above the limit; False without a price.
        """
        item = change.item
        return item is not None and item.price is not None and item.price > self._limit


@register_filter("text_contains")
class TextContains(Filter):
    """Accepts changes whose item mentions a phrase, ignoring case."""

    def __init__(self, phrase: str) -> None:
        """Initialize TextContains.

        Args:
            phrase: Phrase to look for in the item's title and text.
        """
        self._phrase = phrase.casefold()

    def matches(self, change: Change) -> bool:
        """Return whether the item's title or text contains the phrase.

        Args:
            change: The change to evaluate.

        Returns:
            True if the phrase is found; False for a change without an item.
        """
        item = change.item
        if item is None:
            return False
        return self._phrase in item.title.casefold() or self._phrase in item.text.casefold()


@register_filter("matches")
class Matches(Filter):
    """Accepts changes whose item matches a regular expression."""

    def __init__(self, pattern: str) -> None:
        """Initialize Matches.

        Args:
            pattern: Regular expression searched in the item's title and text.

        Raises:
            ValueError: If the pattern is not a valid regular expression.
        """
        try:
            self._regex = re.compile(pattern)
        except re.error as exc:
            msg = f"Invalid regular expression: {pattern!r}"
            raise ValueError(msg) from exc

    def matches(self, change: Change) -> bool:
        """Return whether the pattern is found in the item's title or text.

        Args:
            change: The change to evaluate.

        Returns:
            True if the pattern is found; False for a change without an item.
        """
        item = change.item
        if item is None:
            return False
        return (
            self._regex.search(item.title) is not None or self._regex.search(item.text) is not None
        )
