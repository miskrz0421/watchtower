"""Base Filter interface implementing the Specification pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod

from watchtower.models import Change
from watchtower.registry import register_filter


class Filter(ABC):
    """Abstract specification deciding whether a single Change matters.

    Filters combine with operators into a tree of composite filters:
    `a & b` (both), `a | b` (at least one), `~a` (the opposite).
    """

    @abstractmethod
    def matches(self, change: Change) -> bool:
        """Return whether a change should be kept.

        Filters work on single Changes rather than whole events, so one
        rejected change does not affect the others (see ADR-005).

        Args:
            change: The change to evaluate.

        Returns:
            True if the change passes this filter.
        """

    def __and__(self, other: Filter) -> Filter:
        """Combine with another filter; both must accept a change.

        Args:
            other: Filter on the right of `&`.

        Returns:
            An `And` of the two filters.
        """
        return And(self, other)

    def __or__(self, other: Filter) -> Filter:
        """Combine with another filter; one accepting a change is enough.

        Args:
            other: Filter on the right of `|`.

        Returns:
            An `Or` of the two filters.
        """
        return Or(self, other)

    def __invert__(self) -> Filter:
        """Negate this filter.

        Returns:
            A `Not` of this filter.
        """
        return Not(self)


@register_filter("all")
class And(Filter):
    """Accepts a change that every inner filter accepts.

    The filters are evaluated lazily, False is returned on the first non-matching filter.
    """

    def __init__(self, *filters: Filter) -> None:
        """Initialize And.

        Args:
            *filters: Filters that must all accept a change.
        """
        if len(filters) == 0:
            raise ValueError("At least one filter is required.")
        self._filters = filters

    def matches(self, change: Change) -> bool:
        """Return whether every inner filter accepts the change.

        Args:
            change: The change to evaluate.

        Returns:
            True if all inner filters accept it; True when there are none.
        """
        return all(filter.matches(change) for filter in self._filters)


@register_filter("any")
class Or(Filter):
    """Accepts a change that at least one inner filter accepts.

    The filters are evaluated lazily, True is returned on the first matching filter.
    """

    def __init__(self, *filters: Filter) -> None:
        """Initialize Or.

        Args:
            *filters: Filters of which one must accept a change.
        """
        if len(filters) == 0:
            raise ValueError("At least one filter is required.")
        self._filters = filters

    def matches(self, change: Change) -> bool:
        """Return whether at least one inner filter accepts the change.

        Args:
            change: The change to evaluate.

        Returns:
            True if an inner filter accepts it; False when there are none.
        """
        return any(filter.matches(change) for filter in self._filters)


@register_filter("not")
class Not(Filter):
    """Accepts a change that the inner filter rejects."""

    def __init__(self, inner: Filter) -> None:
        """Initialize Not.

        Args:
            inner: Filter whose answer is reversed.
        """
        self._inner = inner

    def matches(self, change: Change) -> bool:
        """Return whether the inner filter rejects the change.

        Args:
            change: The change to evaluate.

        Returns:
            True if the inner filter rejects it.
        """
        return not self._inner.matches(change)
