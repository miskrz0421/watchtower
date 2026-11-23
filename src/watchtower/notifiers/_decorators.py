"""Notifiers wrapped around other notifiers to send less (Decorator pattern, see ADR-026)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from watchtower._models import ChangeEvent
from watchtower.notifiers._base import Notifier


class RateLimited(Notifier):
    """Passes on only a limited number of events per hour."""

    def __init__(
        self, notifier: Notifier, per_hour: int, now: Callable[[], datetime] = datetime.now
    ) -> None:
        """Initialize RateLimited.

        Args:
            notifier: Notifier to wrap.
            per_hour: How many events are sent within any hour.
            now: Function returning the current time; tests pass a fake one.

        Raises:
            ValueError: If `per_hour` is less than 1.
        """
        raise NotImplementedError

    def send(self, event: ChangeEvent) -> None:
        """Send the event, or log and drop it when the limit is reached.

        Args:
            event: Event to send.

        Raises:
            NotifyError: If the wrapped notifier fails.
        """
        raise NotImplementedError


class QuietHours(Notifier):
    """Passes on no events during some hours of the day."""

    def __init__(
        self,
        notifier: Notifier,
        start: int,
        end: int,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        """Initialize QuietHours.

        Args:
            notifier: Notifier to wrap.
            start: Local hour (0-23) when the quiet time starts.
            end: Local hour (0-23) when it ends; smaller than `start` means the next day.
            now: Function returning the current local time; tests pass a fake one.

        Raises:
            ValueError: If an hour is not in 0-23, or both are the same.
        """
        raise NotImplementedError

    def send(self, event: ChangeEvent) -> None:
        """Send the event, or log and drop it during the quiet hours.

        Args:
            event: Event to send.

        Raises:
            NotifyError: If the wrapped notifier fails.
        """
        raise NotImplementedError
