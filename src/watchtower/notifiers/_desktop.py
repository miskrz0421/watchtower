"""DesktopNotifier showing change events as desktop notifications."""

from __future__ import annotations

from collections.abc import Callable

from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier


@register_notifier("desktop")
class DesktopNotifier(Notifier):
    """Notifier showing each change event as a message from the tray icon.

    It does not import Qt: the GUI connects it to the tray icon (see ADR-024).
    """

    def __init__(self) -> None:
        """Initialize DesktopNotifier, not yet connected to a tray icon."""
        raise NotImplementedError

    def connect(self, show: Callable[[str, str], None]) -> None:
        """Set the function that shows a message; the GUI calls this at start.

        Args:
            show: Called from the engine thread with a title and a message.
        """
        raise NotImplementedError

    def send(self, event: ChangeEvent) -> None:
        """Show the event's summary and changes as one desktop message.

        Args:
            event: Event to show.

        Raises:
            NotifyError: If no GUI is connected.
        """
        raise NotImplementedError
