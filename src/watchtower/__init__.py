"""Watchtower: A plugin-based monitoring framework in Python."""

from watchtower.core.watcher import Watcher
from watchtower.diffs.base import Differ
from watchtower.diffs.items import ItemDiff
from watchtower.diffs.text import TextDiff
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
from watchtower.filters.base import Filter
from watchtower.models import (
    Change,
    ChangeEvent,
    ChangeKind,
    Item,
    ItemDict,
    Snapshot,
    SnapshotDict,
)
from watchtower.notifiers.base import Notifier
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.registry import (
    create,
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
from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource
from watchtower.sources.http import HttpSource
from watchtower.sources.parsing import parse_price
from watchtower.sources.rss import RSSSource
from watchtower.sources.webpage import WebPageSource
from watchtower.storage.snapshots import SnapshotStore

__all__ = [
    "Change",
    "ChangeDetected",
    "ChangeEvent",
    "ChangeKind",
    "CheckCompleted",
    "ConsoleNotifier",
    "Differ",
    "Event",
    "EventBus",
    "FakeSource",
    "FetchFailed",
    "FileSource",
    "Filter",
    "HttpSource",
    "Item",
    "ItemDict",
    "ItemDiff",
    "Notifier",
    "NotifyError",
    "ParseError",
    "RSSSource",
    "Snapshot",
    "SnapshotDict",
    "SnapshotStore",
    "Source",
    "SourceError",
    "StorageError",
    "TextDiff",
    "Watcher",
    "WatcherState",
    "WatcherStateChanged",
    "WatchtowerError",
    "WebPageSource",
    "create",
    "create_differ",
    "create_filter",
    "create_notifier",
    "create_source",
    "list_plugins",
    "parse_price",
    "register_differ",
    "register_filter",
    "register_notifier",
    "register_source",
]
