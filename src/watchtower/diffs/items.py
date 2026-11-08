"""Item-level differ comparing snapshots by item key."""

from __future__ import annotations

from watchtower.diffs.base import Differ
from watchtower.models import Change, ChangeKind, Snapshot
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
        if old is None:
            return []

        old_by_key = {item.key: item for item in old.items}
        new_by_key = {item.key: item for item in new.items}

        changes: list[Change] = []
        for key, item in new_by_key.items():
            before = old_by_key.get(key)
            if before is None:
                changes.append(Change(kind=ChangeKind.NEW, item=item))
            elif before != item:
                changes.append(Change(kind=ChangeKind.CHANGED, item=item, before=before))
        for key, item in old_by_key.items():
            if key not in new_by_key:
                changes.append(Change(kind=ChangeKind.REMOVED, item=item))
        return changes
