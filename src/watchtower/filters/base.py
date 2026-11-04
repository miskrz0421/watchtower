"""Base Filter interface implementing the Specification pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod

from watchtower.models import Change


class Filter(ABC):
    """Abstract specification deciding whether a single Change matters."""

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
