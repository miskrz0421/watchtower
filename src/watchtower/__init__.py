"""Watchtower: A plugin-based monitoring framework in Python."""

from watchtower.core.watcher import Watcher
from watchtower.diffs.base import Differ
from watchtower.diffs.text import TextDiff
from watchtower.errors import (
    NotifyError,
    ParseError,
    SourceError,
    WatchtowerError,
)
from watchtower.events import (
    ChangeDetected,
    CheckCompleted,
    EventBus,
    FetchFailed,
    WatcherStateChanged,
)
from watchtower.models import (
    Change,
    ChangeEvent,
    ChangeKind,
    Item,
    Snapshot,
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

__all__ = [
    "Change",
    "ChangeDetected",
    "ChangeEvent",
    "ChangeKind",
    "CheckCompleted",
    "ConsoleNotifier",
    "Differ",
    "EventBus",
    "FakeSource",
    "FetchFailed",
    "FileSource",
    "Item",
    "Notifier",
    "NotifyError",
    "ParseError",
    "Snapshot",
    "Source",
    "SourceError",
    "TextDiff",
    "Watcher",
    "WatcherStateChanged",
    "WatchtowerError",
    "create",
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
