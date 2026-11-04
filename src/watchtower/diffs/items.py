"""Item-level differ comparing snapshots by item key."""

from __future__ import annotations

from watchtower.diffs.base import Differ
from watchtower.models import Change, Snapshot
from watchtower.registry import register_differ


@register_differ("items")
class ItemDiff(Differ):
    """Detects new, removed and changed items by comparing their keys."""

    def diff(self, old: Snapshot | None, new: Snapshot) -> list[Change]:
        """Compute item-level changes between two snapshots.

        Returns an empty list if old is None (see ADR-004). A changed item
        keeps its previous version in `Change.before`.

        Args:
            old: The previous snapshot, or None if first run.
            new: The current snapshot.

        Returns:
            One Change of kind NEW, REMOVED or CHANGED per differing item.
        """
        raise NotImplementedError
