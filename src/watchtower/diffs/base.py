"""Base Differ interface implementing the Strategy pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod

from watchtower.models import Change, Snapshot


class Differ(ABC):
    """Abstract Strategy interface for detecting differences between snapshots."""

    @abstractmethod
    def diff(self, old: Snapshot | None, new: Snapshot) -> list[Change]:
        """Compute the list of changes between the previous and current snapshot.

        In accordance with ADR-004, if `old` is None (the first run/baseline),
        no changes should be reported.

        Args:
            old: The previous snapshot, or None if this is the first execution.
            new: The newly captured snapshot.

        Returns:
            List of detected Change objects.
        """
