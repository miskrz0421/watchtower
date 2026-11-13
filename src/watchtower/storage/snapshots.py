"""SnapshotStore keeping the last snapshot of each watcher in SQLite."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from watchtower.errors import StorageError
from watchtower.models import Snapshot

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS snapshots (
    watcher_name TEXT PRIMARY KEY,
    data TEXT NOT NULL
)
"""

_SELECT = "SELECT data FROM snapshots WHERE watcher_name = ?"

_UPSERT = """
INSERT INTO snapshots (watcher_name, data) VALUES (?, ?)
ON CONFLICT (watcher_name) DO UPDATE SET data = excluded.data
"""


class SnapshotStore:
    """Saves and restores watcher snapshots (Memento pattern).

    Keeps one row per watcher in the `snapshots` table, holding the last
    snapshot as JSON. Every call opens its own short-lived connection, so a
    store can be used from any thread (see ADR-013).
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize SnapshotStore and create its table if needed.

        Args:
            path: Path to the SQLite database file; created if missing.

        Raises:
            StorageError: If the database cannot be opened.
        """
        self._path = Path(path)
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def load(self, watcher_name: str) -> Snapshot | None:
        """Return the last saved snapshot of a watcher.

        Args:
            watcher_name: Name of the watcher.

        Returns:
            The saved snapshot, or None if the watcher has none yet.

        Raises:
            StorageError: If the database cannot be read or the saved data is invalid.
        """
        with self._connect() as conn:
            row = conn.execute(_SELECT, (watcher_name,)).fetchone()
        if row is None:
            return None
        try:
            return Snapshot.from_dict(json.loads(row[0]))
        except (ValueError, KeyError, TypeError) as err:
            msg = f"Saved snapshot of watcher {watcher_name!r} is invalid: {err}"
            raise StorageError(msg) from err

    def save(self, watcher_name: str, snapshot: Snapshot) -> None:
        """Replace the saved snapshot of a watcher.

        Args:
            watcher_name: Name of the watcher.
            snapshot: Snapshot to remember.

        Raises:
            StorageError: If the database cannot be written.
        """
        data = json.dumps(snapshot.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(_UPSERT, (watcher_name, data))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection for one operation.

        Commits if the block succeeds, rolls back if it raises, and always
        closes the connection. A plain `with sqlite3.connect(...)` would
        commit but leave the connection open.

        Raises:
            StorageError: If SQLite reports an error.
        """
        try:
            conn = sqlite3.connect(self._path)
        except sqlite3.Error as err:
            msg = f"Cannot open snapshot database {self._path}: {err}"
            raise StorageError(msg) from err
        try:
            with conn:
                yield conn
        except sqlite3.Error as err:
            msg = f"Snapshot database {self._path} failed: {err}"
            raise StorageError(msg) from err
        finally:
            conn.close()
