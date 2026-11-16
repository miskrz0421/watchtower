"""HistoryStore keeping every reported change and every check in SQLite."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from dedent import dedent

from watchtower._errors import StorageError
from watchtower._events import CheckCompleted
from watchtower._models import Change, ChangeEvent, ChangeKind

_CREATE_CHANGES_TABLE = dedent("""
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watcher_name TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        kind TEXT NOT NULL,
        key TEXT,
        title TEXT,
        price REAL,
        old_price REAL
    )
    """)

_CREATE_CHECKS_TABLE = dedent("""
    CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watcher_name TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        ok INTEGER NOT NULL,
        duration_seconds REAL NOT NULL,
        error TEXT
    )
    """)

_INSERT_CHANGE = dedent("""
    INSERT INTO changes (watcher_name, timestamp, kind, key, title, price, old_price)
    VALUES (:watcher_name, :timestamp, :kind, :key, :title, :price, :old_price)
    """)

_INSERT_CHECK = dedent("""
    INSERT INTO checks (watcher_name, timestamp, ok, duration_seconds, error)
    VALUES (:watcher_name, :timestamp, :ok, :duration_seconds, :error)
    """)

_SELECT_CHANGES = dedent("""
    SELECT watcher_name, timestamp, kind, key, title, price, old_price
    FROM changes
    ORDER BY id ASC
    """)

_SELECT_CHANGES_FOR_WATCHER = dedent("""
    SELECT watcher_name, timestamp, kind, key, title, price, old_price
    FROM changes
    WHERE watcher_name = ?
    ORDER BY id ASC
    """)

_SELECT_CHECKS = dedent("""
    SELECT watcher_name, timestamp, ok, duration_seconds, error
    FROM checks
    ORDER BY id ASC
    """)

_SELECT_CHECKS_FOR_WATCHER = dedent("""
    SELECT watcher_name, timestamp, ok, duration_seconds, error
    FROM checks
    WHERE watcher_name = ?
    ORDER BY id ASC
    """)


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


class _ChangeRow(TypedDict):
    """Raw database row representation for inserting a change."""

    watcher_name: str
    timestamp: str
    kind: str
    key: str | None
    title: str | None
    price: float | None
    old_price: float | None


class _CheckRow(TypedDict):
    """Raw database row representation for inserting a check."""

    watcher_name: str
    timestamp: str
    ok: int
    duration_seconds: float
    error: str | None


def _change_to_row(
    watcher_name: str,
    timestamp_iso: str,
    change: Change,
) -> _ChangeRow:
    """Convert a single Change into a typed database row mapping."""
    item = change.item if change.item is not None else change.before
    return {
        "watcher_name": watcher_name,
        "timestamp": timestamp_iso,
        "kind": change.kind.value,
        "key": item.key if item is not None else None,
        "title": item.title if item is not None else None,
        "price": change.item.price if change.item is not None else None,
        "old_price": change.before.price if change.before is not None else None,
    }


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
        self._path = Path(path)
        with self._connect() as conn:
            conn.execute(_CREATE_CHANGES_TABLE)
            conn.execute(_CREATE_CHECKS_TABLE)

    def record_changes(self, event: ChangeEvent) -> None:
        """Save one row per change of an event.

        Args:
            event: Event a watcher reported.

        Raises:
            StorageError: If the database cannot be written.
        """
        if not event.changes:
            return
        timestamp_iso = event.timestamp.isoformat()
        rows = [
            _change_to_row(event.watcher_name, timestamp_iso, change) for change in event.changes
        ]
        with self._connect() as conn:
            conn.executemany(_INSERT_CHANGE, rows)

    def record_check(self, check: CheckCompleted) -> None:
        """Save one row for a finished check, successful or not.

        Args:
            check: Event published at the end of the check.

        Raises:
            StorageError: If the database cannot be written.
        """
        row: _CheckRow = {
            "watcher_name": check.watcher_name,
            "timestamp": check.timestamp.isoformat(),
            "ok": int(check.ok),
            "duration_seconds": check.duration_seconds,
            "error": check.error,
        }
        with self._connect() as conn:
            conn.execute(_INSERT_CHECK, row)

    def changes(self, watcher_name: str | None = None) -> Iterator[ChangeRecord]:
        """Read saved changes one row at a time, oldest first.

        Args:
            watcher_name: Only this watcher's changes; None means all watchers.

        Yields:
            The saved changes, without loading the whole table into memory.

        Raises:
            StorageError: If the database cannot be read.
        """
        sql = _SELECT_CHANGES if watcher_name is None else _SELECT_CHANGES_FOR_WATCHER
        params = () if watcher_name is None else (watcher_name,)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor:
                try:
                    timestamp = datetime.fromisoformat(row[1])
                    kind = ChangeKind(row[2])
                except (ValueError, TypeError) as err:
                    msg = f"Saved change in {self._path} is invalid: {err}"
                    raise StorageError(msg) from err
                yield ChangeRecord(
                    watcher_name=row[0],
                    timestamp=timestamp,
                    kind=kind,
                    key=row[3],
                    title=row[4],
                    price=row[5],
                    old_price=row[6],
                )

    def checks(self, watcher_name: str | None = None) -> Iterator[CheckRecord]:
        """Read saved checks one row at a time, oldest first.

        Args:
            watcher_name: Only this watcher's checks; None means all watchers.

        Yields:
            The saved checks, without loading the whole table into memory.

        Raises:
            StorageError: If the database cannot be read.
        """
        sql = _SELECT_CHECKS if watcher_name is None else _SELECT_CHECKS_FOR_WATCHER
        params = () if watcher_name is None else (watcher_name,)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor:
                try:
                    timestamp = datetime.fromisoformat(row[1])
                except (ValueError, TypeError) as err:
                    msg = f"Saved check in {self._path} is invalid: {err}"
                    raise StorageError(msg) from err
                yield CheckRecord(
                    watcher_name=row[0],
                    timestamp=timestamp,
                    ok=bool(row[2]),
                    duration_seconds=float(row[3]),
                    error=row[4],
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection for one operation.

        Commits if the block succeeds, rolls back if it raises, and always
        closes the connection.

        Yields:
            The open connection.

        Raises:
            StorageError: If SQLite reports an error.
        """
        try:
            conn = sqlite3.connect(self._path)
        except sqlite3.Error as err:
            msg = f"Cannot open history database {self._path}: {err}"
            raise StorageError(msg) from err
        try:
            with conn:
                yield conn
        except sqlite3.Error as err:
            msg = f"History database {self._path} failed: {err}"
            raise StorageError(msg) from err
        finally:
            conn.close()
