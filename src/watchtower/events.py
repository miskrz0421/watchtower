"""Event definitions and the central EventBus (Observer pattern)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

from watchtower.models import ChangeEvent

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


class WatcherState(StrEnum):
    """Enumeration of possible watcher runtime states."""

    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(frozen=True, kw_only=True)
class Event:
    """Base class for all events dispatched via EventBus."""

    timestamp: datetime = field(default_factory=_utc_now)


T = TypeVar("T", bound=Event)


@dataclass(frozen=True)
class CheckCompleted(Event):
    """Published after every check execution, capturing duration and status."""

    watcher_name: str
    duration_seconds: float
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class ChangeDetected(Event):
    """Published when changes are detected and pass configured filters."""

    watcher_name: str
    event: ChangeEvent


@dataclass(frozen=True)
class FetchFailed(Event):
    """Published when a source fetch operation fails permanently."""

    watcher_name: str
    error: str


@dataclass(frozen=True)
class WatcherStateChanged(Event):
    """Published whenever a watcher transitions between runtime states."""

    watcher_name: str
    old_state: WatcherState
    new_state: WatcherState


class EventBus:
    """Synchronous in-memory event bus implementing the Observer pattern.

    Subscribers register callbacks for specific event classes. Publishing
    an event dispatches it to all matching subscribers. Exceptions in
    individual subscribers are logged and do not prevent other subscribers
    from receiving the event.
    """

    def __init__(self) -> None:
        """Initialize an empty EventBus with no subscribers."""
        self._subscribers: dict[type[Event], list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Register an event handler for a specific event class.

        Args:
            event_type: The event class type to subscribe to.
            handler: Callable taking the event instance as its sole argument.
        """
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Unregister a previously subscribed event handler.

        Args:
            event_type: The event class type.
            handler: The callable to remove.
        """
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        """Dispatch an event synchronously to all registered subscribers.

        Also notifies subscribers subscribed to any base class of the event.
        Exceptions raised by handlers are caught and logged so that other
        handlers are not impacted.

        Args:
            event: The event instance to publish.
        """
        event_cls = type(event)
        for subscribed_cls, handlers in self._subscribers.items():
            if issubclass(event_cls, subscribed_cls):
                for handler in list(handlers):
                    try:
                        handler(event)
                    except Exception:
                        logger.exception(
                            "Unhandled exception in subscriber %r for event %r",
                            handler,
                            event,
                        )
