"""Event definitions and the central EventBus (Observer pattern)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from watchtower.models import ChangeEvent

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class CheckCompleted:
    """Published after every check execution, capturing duration and status."""

    watcher_name: str
    duration_seconds: float
    ok: bool
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ChangeDetected:
    """Published when changes are detected and pass configured filters."""

    watcher_name: str
    event: ChangeEvent
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class FetchFailed:
    """Published when a source fetch operation fails permanently."""

    watcher_name: str
    error: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class WatcherStateChanged:
    """Published whenever a watcher transitions between runtime states."""

    watcher_name: str
    old_state: str
    new_state: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Synchronous in-memory event bus implementing the Observer pattern.

    Subscribers register callbacks for specific event classes. Publishing
    an event dispatches it to all matching subscribers. Exceptions in
    individual subscribers are logged and do not prevent other subscribers
    from receiving the event.
    """

    def __init__(self) -> None:
        """Initialize an empty EventBus with no subscribers."""
        self._subscribers: dict[type[Any], list[Callable[[Any], None]]] = defaultdict(list)

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

    def publish(self, event: Any) -> None:
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
