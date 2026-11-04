"""SnapshotStore keeping the last snapshot of each watcher in SQLite."""

from __future__ import annotations

from pathlib import Path

from watchtower.models import Snapshot


class SnapshotStore:
    """Saves and restores watcher snapshots (Memento pattern)."""

    def __init__(self, path: str | Path) -> None:
        """Initialize SnapshotStore.

        Args:
            path: Path to the SQLite database file.
        """
        self.path = Path(path)

    def load(self, watcher_name: str) -> Snapshot | None:
        """Return the last saved snapshot of a watcher.

        Args:
            watcher_name: Name of the watcher.

        Returns:
            The saved snapshot, or None if the watcher has none yet.
        """
        raise NotImplementedError

    def save(self, watcher_name: str, snapshot: Snapshot) -> None:
        """Replace the saved snapshot of a watcher.

        Args:
            watcher_name: Name of the watcher.
            snapshot: Snapshot to remember.
        """
        raise NotImplementedError
