"""Composite filters combining other filters (Composite pattern)."""

from __future__ import annotations

from watchtower.filters.base import Filter
from watchtower.models import Change
from watchtower.registry import register_filter


@register_filter("all")
class And(Filter):
    """Accepts a change that every inner filter accepts."""

    def __init__(self, *filters: Filter) -> None:
        """Initialize And.

        Args:
            *filters: Filters that must all accept a change.
        """
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether every inner filter accepts the change.

        Args:
            change: The change to evaluate.

        Returns:
            True if all inner filters accept it; True when there are none.
        """
        raise NotImplementedError


@register_filter("any")
class Or(Filter):
    """Accepts a change that at least one inner filter accepts."""

    def __init__(self, *filters: Filter) -> None:
        """Initialize Or.

        Args:
            *filters: Filters of which one must accept a change.
        """
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether at least one inner filter accepts the change.

        Args:
            change: The change to evaluate.

        Returns:
            True if an inner filter accepts it; False when there are none.
        """
        raise NotImplementedError


@register_filter("not")
class Not(Filter):
    """Accepts a change that the inner filter rejects."""

    def __init__(self, inner: Filter) -> None:
        """Initialize Not.

        Args:
            inner: Filter whose answer is reversed.
        """
        raise NotImplementedError

    def matches(self, change: Change) -> bool:
        """Return whether the inner filter rejects the change.

        Args:
            change: The change to evaluate.

        Returns:
            True if the inner filter rejects it.
        """
        raise NotImplementedError
