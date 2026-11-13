"""Core Watcher orchestrating the monitoring pipeline."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from watchtower.diffs.base import Differ
from watchtower.events import ChangeDetected, CheckCompleted, Event, EventBus, FetchFailed
from watchtower.models import Change, ChangeEvent, Snapshot
from watchtower.notifiers.base import Notifier
from watchtower.sources.base import Source
from watchtower.storage.snapshots import SnapshotStore

_logger = logging.getLogger(__name__)


class Watcher:
    """Orchestrates snapshot capture, diffing, and notification.

    Maintains current state for a single monitored target. Emits lifecycle
    and detection events to the central EventBus for global observers (such
    as history recorders and UI bridges) while dispatching ChangeEvents
    directly to its configured Notifiers.

    With a SnapshotStore, the previous snapshot is loaded from the store on
    every check and the new one is saved after notifying, so the watcher
    remembers its state across restarts. Without a store, it only remembers
    the last snapshot in memory (see ADR-013).
    """

    def __init__(
        self,
        name: str,
        source: Source,
        differ: Differ,
        notifiers: Sequence[Notifier] | None = None,
        event_bus: EventBus | None = None,
        store: SnapshotStore | None = None,
    ) -> None:
        """Initialize a Watcher pipeline.

        Args:
            name: Human-readable identifier for this watcher.
            source: Source strategy used to acquire state snapshots.
            differ: Differ strategy used to detect changes against previous snapshot.
            notifiers: Target notifiers that will receive detected change events.
            event_bus: Optional global event bus for system-wide observers.
            store: Optional store that keeps the last snapshot between runs.
        """
        self._name = name
        self._source = source
        self._differ = differ
        self._notifiers: list[Notifier] = list(notifiers) if notifiers is not None else []
        self._event_bus = event_bus
        self._store = store
        self._last_snapshot: Snapshot | None = None

    @property
    def name(self) -> str:
        """Human-readable identifier for this watcher."""
        return self._name

    @property
    def source(self) -> Source:
        """Source strategy used to acquire state snapshots."""
        return self._source

    @property
    def differ(self) -> Differ:
        """Differ strategy used to detect changes against previous snapshot."""
        return self._differ

    @property
    def notifiers(self) -> list[Notifier]:
        """Target notifiers configured for this watcher."""
        return self._notifiers

    @property
    def event_bus(self) -> EventBus | None:
        """Global event bus, if configured."""
        return self._event_bus

    @property
    def store(self) -> SnapshotStore | None:
        """Store keeping the last snapshot between runs, if configured."""
        return self._store

    @property
    def last_snapshot(self) -> Snapshot | None:
        """Most recently captured snapshot, or None if no check has run yet."""
        return self._last_snapshot

    def _emit(self, event: Event) -> None:
        """Publish an event to the EventBus if one is configured.

        Args:
            event: Event to publish.
        """
        if self._event_bus is not None:
            self._event_bus.publish(event)

    def _previous_snapshot(self) -> Snapshot | None:
        """Return the snapshot to compare against, from the store if there is one.

        Returns:
            The previous snapshot, or None before the first check.
        """
        if self._store is not None:
            return self._store.load(self._name)
        return self._last_snapshot

    def _remember(self, snapshot: Snapshot) -> None:
        """Keep the snapshot as the baseline for the next check.

        Args:
            snapshot: Snapshot taken by the current check.

        Raises:
            StorageError: If the store cannot save it.
        """
        self._last_snapshot = snapshot
        if self._store is not None:
            self._store.save(self._name, snapshot)

    def _fetch_and_diff(self) -> tuple[list[Change], Snapshot]:
        """Fetch a new snapshot and compute changes against previous snapshot.

        Returns:
            The detected changes and the new snapshot.

        Raises:
            WatchtowerError: If the source or the store fails.
        """
        new_snapshot = self._source.snapshot()
        changes = self._differ.diff(self._previous_snapshot(), new_snapshot)
        return changes, new_snapshot

    def _dispatch_notifiers(self, event: ChangeEvent) -> None:
        """Deliver a ChangeEvent to all configured notifiers.

        Args:
            event: Event to deliver.
        """
        for notifier in self._notifiers:
            try:
                notifier.send(event)
            except Exception:
                _logger.exception("Notifier %r failed for watcher %r", notifier, self._name)

    def _handle_changes(self, changes: list[Change], timestamp: datetime) -> ChangeEvent:
        """Construct ChangeEvent, dispatch to notifiers, and publish ChangeDetected.

        Args:
            changes: Changes found by the differ; never empty.
            timestamp: Time of the check.

        Returns:
            The event that was sent.
        """
        summary = f"{len(changes)} change(s) detected"
        event = ChangeEvent(
            watcher_name=self._name,
            timestamp=timestamp,
            changes=tuple(changes),
            summary=summary,
        )
        self._dispatch_notifiers(event)
        self._emit(
            ChangeDetected(
                watcher_name=self._name,
                event=event,
                timestamp=timestamp,
            )
        )
        return event

    def _emit_failure(self, err: Exception, duration: float, timestamp: datetime) -> None:
        """Emit failure lifecycle events to the event bus.

        Args:
            err: Error that stopped the check.
            duration: Seconds the check ran before failing.
            timestamp: Time of the check.
        """
        self._emit(
            FetchFailed(
                watcher_name=self._name,
                error=str(err),
                timestamp=timestamp,
            )
        )
        self._emit(
            CheckCompleted(
                watcher_name=self._name,
                duration_seconds=duration,
                ok=False,
                error=str(err),
                timestamp=timestamp,
            )
        )

    def check_once(self) -> ChangeEvent | None:
        """Execute a single check cycle through the monitoring pipeline.

        1. Fetches a new snapshot from the configured source.
        2. Loads the previous snapshot and computes changes against it.
        3. If changes are detected, constructs a ChangeEvent, sends it to all
           configured notifiers, and publishes ChangeDetected on the EventBus.
        4. Saves the new snapshot as the baseline for the next check. This
           happens after notifying, so a failed save can repeat an alert but
           never lose one. A failed fetch saves nothing.
        5. Publishes CheckCompleted with execution status and duration.

        Returns:
            The generated ChangeEvent if changes were detected, otherwise None.

        Raises:
            WatchtowerError: If an unhandled source or differ error occurs.
        """
        start_time = time.perf_counter()
        now = datetime.now(UTC)

        try:
            changes, new_snapshot = self._fetch_and_diff()

            event: ChangeEvent | None = None
            if changes:
                event = self._handle_changes(changes, now)
            self._remember(new_snapshot)

            duration = time.perf_counter() - start_time
            self._emit(
                CheckCompleted(
                    watcher_name=self._name,
                    duration_seconds=duration,
                    ok=True,
                    timestamp=now,
                )
            )
            return event

        except Exception as err:
            duration = time.perf_counter() - start_time
            self._emit_failure(err, duration, now)
            raise
