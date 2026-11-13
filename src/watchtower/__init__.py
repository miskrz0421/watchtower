"""Watchtower: a plugin-based monitoring framework.

The names below are the public API: what is needed to build a watcher in code
and to write a plugin. Built-in plugins are not listed here; import them from
their packages (`watchtower.sources`, `watchtower.diffs`, `watchtower.notifiers`)
or create them by name through the registry (see ADR-015).

Importing this package imports those packages too, which registers every
built-in plugin.
"""

from watchtower.core import Watcher
from watchtower.diffs import Differ
from watchtower.errors import (
    NotifyError,
    ParseError,
    SourceError,
    StorageError,
    WatchtowerError,
)
from watchtower.events import (
    ChangeDetected,
    CheckCompleted,
    Event,
    EventBus,
    FetchFailed,
    WatcherState,
    WatcherStateChanged,
)
from watchtower.filters import Filter
from watchtower.models import Change, ChangeEvent, ChangeKind, Item, Snapshot
from watchtower.notifiers import Notifier
from watchtower.registry import (
    create_differ,
    create_filter,
    create_notifier,
    create_source,
    list_plugins,
    register_differ,
    register_filter,
    register_notifier,
    register_source,
)
from watchtower.sources import Source
from watchtower.storage import SnapshotStore

__all__ = [
    "Change",
    "ChangeDetected",
    "ChangeEvent",
    "ChangeKind",
    "CheckCompleted",
    "Differ",
    "Event",
    "EventBus",
    "FetchFailed",
    "Filter",
    "Item",
    "Notifier",
    "NotifyError",
    "ParseError",
    "Snapshot",
    "SnapshotStore",
    "Source",
    "SourceError",
    "StorageError",
    "Watcher",
    "WatcherState",
    "WatcherStateChanged",
    "WatchtowerError",
    "create_differ",
    "create_filter",
    "create_notifier",
    "create_source",
    "list_plugins",
    "register_differ",
    "register_filter",
    "register_notifier",
    "register_source",
]
