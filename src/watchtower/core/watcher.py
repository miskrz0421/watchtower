"""Core Watcher orchestrating the monitoring pipeline."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from watchtower.diffs.base import Differ
from watchtower.events import ChangeDetected, CheckCompleted, EventBus, FetchFailed
from watchtower.models import ChangeEvent, Snapshot
from watchtower.notifiers.base import Notifier
from watchtower.sources.base import Source

logger = logging.getLogger(__name__)


class Watcher:
    """Orchestrates snapshot capture, diffing, filtering, and notification.

    Maintains current state for a single monitored target. Emits lifecycle
    and detection events to the central EventBus for global observers (such
    as history recorders and UI bridges) while dispatching ChangeEvents
    directly to its configured Notifiers.
    """

    def __init__(
        self,
        name: str,
        source: Source,
        differ: Differ,
        notifiers: Sequence[Notifier] | None = None,
        event_bus: EventBus | None = None,
        initial_snapshot: Snapshot | None = None,
    ) -> None:
        """Initialize a Watcher pipeline.

        Args:
            name: Human-readable identifier for this watcher.
            source: Source strategy used to acquire state snapshots.
            differ: Differ strategy used to detect changes against previous snapshot.
            notifiers: Target notifiers that will receive detected change events.
            event_bus: Optional global event bus for system-wide observers.
            initial_snapshot: Optional starting baseline snapshot.
        """
        self.name = name
        self.source = source
        self.differ = differ
        self.notifiers: list[Notifier] = list(notifiers) if notifiers is not None else []
        self.event_bus = event_bus
        self.last_snapshot = initial_snapshot

    def check_once(self) -> ChangeEvent | None:
        """Execute a single check cycle through the monitoring pipeline.

        1. Fetches a new snapshot from the configured source.
        2. Computes changes against the previous snapshot.
        3. Updates the stored snapshot reference.
        4. If changes are detected, constructs a ChangeEvent, sends it to all
           configured notifiers, and publishes ChangeDetected on the EventBus.
        5. Publishes CheckCompleted with execution status and duration.

        Returns:
            The generated ChangeEvent if changes were detected, otherwise None.

        Raises:
            WatchtowerError: If an unhandled source or differ error occurs.
        """
        start_time = time.perf_counter()
        now = datetime.now(UTC)

        try:
            new_snapshot = self.source.snapshot()
            changes = self.differ.diff(self.last_snapshot, new_snapshot)
            self.last_snapshot = new_snapshot

            event: ChangeEvent | None = None
            if changes:
                summary = f"{len(changes)} change(s) detected"
                event = ChangeEvent(
                    watcher_name=self.name,
                    timestamp=now,
                    changes=tuple(changes),
                    summary=summary,
                )

                # Direct dispatch to this watcher's configured notifiers
                for notifier in self.notifiers:
                    try:
                        notifier.send(event)
                    except Exception:
                        logger.exception("Notifier %r failed for watcher %r", notifier, self.name)

                # Global notification on the event bus
                if self.event_bus is not None:
                    self.event_bus.publish(
                        ChangeDetected(
                            watcher_name=self.name,
                            event=event,
                            timestamp=now,
                        )
                    )

            duration = time.perf_counter() - start_time
            if self.event_bus is not None:
                self.event_bus.publish(
                    CheckCompleted(
                        watcher_name=self.name,
                        duration_seconds=duration,
                        ok=True,
                        timestamp=now,
                    )
                )

            return event

        except Exception as err:
            duration = time.perf_counter() - start_time
            if self.event_bus is not None:
                self.event_bus.publish(
                    FetchFailed(
                        watcher_name=self.name,
                        error=str(err),
                        timestamp=now,
                    )
                )
                self.event_bus.publish(
                    CheckCompleted(
                        watcher_name=self.name,
                        duration_seconds=duration,
                        ok=False,
                        error=str(err),
                        timestamp=now,
                    )
                )
            raise
