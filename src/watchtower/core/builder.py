"""Fluent builder for watchers (Builder pattern)."""

from __future__ import annotations

from datetime import timedelta
from typing import Self

from watchtower.core.watcher import Watcher
from watchtower.diffs.base import Differ
from watchtower.events import EventBus
from watchtower.filters.base import Filter
from watchtower.notifiers.base import Notifier
from watchtower.sources.base import Source
from watchtower.storage.snapshots import SnapshotStore


class WatcherBuilder:
    """Collects the parts of a watcher step by step, then builds it.

    Every step returns the builder, so calls chain:
    `WatcherBuilder("Flats").source(...).every("15m").diff(...).build()`.
    The YAML loader uses the same builder, so a watcher from a config file
    and one written in Python are made the same way (see ADR-018).
    """

    def __init__(self, name: str) -> None:
        """Initialize WatcherBuilder.

        Args:
            name: Name of the watcher to build.
        """
        raise NotImplementedError

    def source(self, source: Source) -> Self:
        """Set where the watcher gets its data.

        Args:
            source: Source to take snapshots from.

        Returns:
            This builder.
        """
        raise NotImplementedError

    def every(self, interval: timedelta | str) -> Self:
        """Set how often the watcher is checked.

        Args:
            interval: Time between checks, as a timedelta or text such as `15m`.

        Returns:
            This builder.

        Raises:
            ConfigError: If the text is not a valid interval.
        """
        raise NotImplementedError

    def diff(self, differ: Differ) -> Self:
        """Set how two snapshots are compared.

        Args:
            differ: Differ to use.

        Returns:
            This builder.
        """
        raise NotImplementedError

    def only_if(self, *filters: Filter) -> Self:
        """Add filters; a change is reported only if it passes all of them.

        Args:
            *filters: Filters to add to the ones already set.

        Returns:
            This builder.
        """
        raise NotImplementedError

    def notify(self, *notifiers: Notifier) -> Self:
        """Add notifiers that receive the reported changes.

        Args:
            *notifiers: Notifiers to add to the ones already set.

        Returns:
            This builder.
        """
        raise NotImplementedError

    def store(self, store: SnapshotStore) -> Self:
        """Set the store that keeps the last snapshot between runs.

        Args:
            store: Store to use.

        Returns:
            This builder.
        """
        raise NotImplementedError

    def event_bus(self, event_bus: EventBus) -> Self:
        """Set the bus the watcher publishes its events on.

        Args:
            event_bus: Bus shared by all watchers.

        Returns:
            This builder.
        """
        raise NotImplementedError

    def build(self) -> Watcher:
        """Create the watcher from the collected parts.

        Returns:
            A new watcher; calling `build` again gives another one.

        Raises:
            ConfigError: If the source or the differ was not set.
        """
        raise NotImplementedError
