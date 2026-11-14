"""Fluent builder for watchers (Builder pattern)."""

from __future__ import annotations

from datetime import timedelta
from typing import Self

from watchtower.core.watcher import DEFAULT_INTERVAL, Watcher
from watchtower.diffs.base import Differ
from watchtower.errors import ConfigError
from watchtower.events import EventBus
from watchtower.filters.base import Filter
from watchtower.notifiers.base import Notifier
from watchtower.sources.base import Source
from watchtower.storage.snapshots import SnapshotStore


class WatcherBuilder:
    """Collects the parts of a watcher step by step, then builds it.

    Every step returns the builder, so calls chain:
    `WatcherBuilder("Flats").source(...).every(timedelta(minutes=15)).diff(...).build()`.
    The YAML loader uses the same builder, so a watcher from a config file
    and one written in Python are made the same way (see ADR-018).
    """

    def __init__(self, name: str) -> None:
        """Initialize WatcherBuilder.

        Args:
            name: Name of the watcher to build.
        """
        self._name = name
        self._source: Source | None = None
        self._differ: Differ | None = None
        self._interval = DEFAULT_INTERVAL
        self._filters: list[Filter] = []
        self._notifiers: list[Notifier] = []
        self._store: SnapshotStore | None = None
        self._event_bus: EventBus | None = None

    def source(self, source: Source) -> Self:
        """Set where the watcher gets its data.

        Args:
            source: Source to take snapshots from.

        Returns:
            This builder.
        """
        self._source = source
        return self

    def every(self, interval: timedelta) -> Self:
        """Set how often the watcher is checked.

        Args:
            interval: Time between checks.

        Returns:
            This builder.

        Raises:
            ConfigError: If the interval is not positive.
        """
        if interval <= timedelta(0):
            msg = f"Watcher {self._name!r}: interval must be positive, got {interval}"
            raise ConfigError(msg)
        self._interval = interval
        return self

    def diff(self, differ: Differ) -> Self:
        """Set how two snapshots are compared.

        Args:
            differ: Differ to use.

        Returns:
            This builder.
        """
        self._differ = differ
        return self

    def only_if(self, *filters: Filter) -> Self:
        """Add filters; a change is reported only if it passes all of them.

        Args:
            *filters: Filters to add to the ones already set.

        Returns:
            This builder.
        """
        self._filters.extend(filters)
        return self

    def notify(self, *notifiers: Notifier) -> Self:
        """Add notifiers that receive the reported changes.

        Args:
            *notifiers: Notifiers to add to the ones already set.

        Returns:
            This builder.
        """
        self._notifiers.extend(notifiers)
        return self

    def store(self, store: SnapshotStore) -> Self:
        """Set the store that keeps the last snapshot between runs.

        Args:
            store: Store to use.

        Returns:
            This builder.
        """
        self._store = store
        return self

    def event_bus(self, event_bus: EventBus) -> Self:
        """Set the bus the watcher publishes its events on.

        Args:
            event_bus: Bus shared by all watchers.

        Returns:
            This builder.
        """
        self._event_bus = event_bus
        return self

    def build(self) -> Watcher:
        """Create the watcher from the collected parts.

        Returns:
            A new watcher; calling `build` again gives another one.

        Raises:
            ConfigError: If the source or the differ was not set.
        """
        if self._source is None:
            msg = f"Watcher {self._name!r} has no source"
            raise ConfigError(msg)
        if self._differ is None:
            msg = f"Watcher {self._name!r} has no differ"
            raise ConfigError(msg)
        return Watcher(
            name=self._name,
            source=self._source,
            differ=self._differ,
            notifiers=self._notifiers,
            event_bus=self._event_bus,
            store=self._store,
            filters=self._filters,
            interval=self._interval,
        )
