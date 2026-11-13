"""HistoryStore keeping every reported change and every check in SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from watchtower.events import CheckCompleted
from watchtower.models import ChangeEvent, ChangeKind


@dataclass(frozen=True)
class ChangeRecord:
    """One reported change, as saved in the `changes` table."""

    watcher_name: str
    timestamp: datetime
    kind: ChangeKind
    key: str | None
    title: str | None
    price: float | None
    old_price: float | None


@dataclass(frozen=True)
class CheckRecord:
    """One check of a watcher, as saved in the `checks` table."""

    watcher_name: str
    timestamp: datetime
    ok: bool
    duration_seconds: float
    error: str | None


class HistoryStore:
    """Appends changes and checks to SQLite and reads them back.

    Lives in the same database file as SnapshotStore and, like it, opens a
    new connection for every call, so it can be used from any thread (see
    ADR-013).
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize HistoryStore and create its tables if needed.

        Args:
            path: Path to the SQLite database file; created if missing.

        Raises:
            StorageError: If the database cannot be opened.
        """
        raise NotImplementedError

    def record_changes(self, event: ChangeEvent) -> None:
        """Save one row per change of an event.

        Args:
            event: Event a watcher reported.

        Raises:
            StorageError: If the database cannot be written.
        """
        raise NotImplementedError

    def record_check(self, check: CheckCompleted) -> None:
        """Save one row for a finished check, successful or not.

        Args:
            check: Event published at the end of the check.

        Raises:
            StorageError: If the database cannot be written.
        """
        raise NotImplementedError

    def changes(self, watcher_name: str | None = None) -> Iterator[ChangeRecord]:
        """Read saved changes one row at a time, oldest first.

        Args:
            watcher_name: Only this watcher's changes; None means all watchers.

        Yields:
            The saved changes, without loading the whole table into memory.

        Raises:
            StorageError: If the database cannot be read.
        """
        raise NotImplementedError

    def checks(self, watcher_name: str | None = None) -> Iterator[CheckRecord]:
        """Read saved checks one row at a time, oldest first.

        Args:
            watcher_name: Only this watcher's checks; None means all watchers.

        Yields:
            The saved checks, without loading the whole table into memory.

        Raises:
            StorageError: If the database cannot be read.
        """
        raise NotImplementedError
