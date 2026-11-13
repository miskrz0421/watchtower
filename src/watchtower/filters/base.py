"""Base Filter interface implementing the Specification pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod

from watchtower.models import Change


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
        raise NotImplementedError

    def __or__(self, other: Filter) -> Filter:
        """Combine with another filter; one accepting a change is enough.

        Args:
            other: Filter on the right of `|`.

        Returns:
            An `Or` of the two filters.
        """
        raise NotImplementedError

    def __invert__(self) -> Filter:
        """Negate this filter.

        Returns:
            A `Not` of this filter.
        """
        raise NotImplementedError
