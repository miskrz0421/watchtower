"""DesktopNotifier showing change events as desktop notifications."""

from __future__ import annotations

from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier


@register_notifier("desktop")
class DesktopNotifier(Notifier):
    """Notifier showing each change event as a notification of the operating system.

    Uses the `desktop-notifier` package, not Qt, so it works in `watchtower run`
    as well as in the tray app (see ADR-024).
    """

    def __init__(self) -> None:
        """Initialize DesktopNotifier."""
        raise NotImplementedError

    def send(self, event: ChangeEvent) -> None:
        """Show the event's summary and changes as one desktop notification.

        Args:
            event: Event to show.

        Raises:
            NotifyError: If the system cannot show the notification.
        """
        raise NotImplementedError
