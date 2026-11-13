"""Built-in filters for the most common rules."""

from __future__ import annotations

from watchtower.filters.base import Filter
from watchtower.models import Change
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
        raise NotImplementedError


@register_filter("price_below")
class PriceBelow(Filter):
    """Accepts changes whose item costs less than a limit."""

    def __init__(self, limit: float) -> None:
        """Initialize PriceBelow.

        Args:
            limit: Price the item must be below.
        """
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether the item's price is below the limit.

        Args:
            change: The change to evaluate.

        Returns:
            True if the item has a price below the limit; False without a price.
        """
        raise NotImplementedError


@register_filter("price_above")
class PriceAbove(Filter):
    """Accepts changes whose item costs more than a limit."""

    def __init__(self, limit: float) -> None:
        """Initialize PriceAbove.

        Args:
            limit: Price the item must be above.
        """
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether the item's price is above the limit.

        Args:
            change: The change to evaluate.

        Returns:
            True if the item has a price above the limit; False without a price.
        """
        raise NotImplementedError


@register_filter("text_contains")
class TextContains(Filter):
    """Accepts changes whose item mentions a phrase, ignoring case."""

    def __init__(self, phrase: str) -> None:
        """Initialize TextContains.

        Args:
            phrase: Phrase to look for in the item's title and text.
        """
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether the item's title or text contains the phrase.

        Args:
            change: The change to evaluate.

        Returns:
            True if the phrase is found; False for a change without an item.
        """
        raise NotImplementedError


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
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether the pattern is found in the item's title or text.

        Args:
            change: The change to evaluate.

        Returns:
            True if the pattern is found; False for a change without an item.
        """
        raise NotImplementedError
