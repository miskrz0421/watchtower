"""DesktopNotifier showing change events as desktop notifications."""

from __future__ import annotations

from typing import TYPE_CHECKING

from watchtower._errors import MissingDependencyError
from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier

if TYPE_CHECKING:
    from desktop_notifier.sync import DesktopNotifierSync


@register_notifier("desktop")
class DesktopNotifier(Notifier):
    """Notifier showing each change event as a notification of the operating system.

    Uses the `desktop-notifier` package, not Qt, so it works in `watchtower run`
    as well as in the tray app (see ADR-024).
    """

    def __init__(self) -> None:
        """Initialize DesktopNotifier.

        The optional package is imported here, not at module import time, so
        `import watchtower` works in a headless install (see ADR-003).

        Raises:
            MissingDependencyError: If the desktop-notifier package is not installed.
        """
        try:
            from desktop_notifier.sync import DesktopNotifierSync
        except ImportError as e:
            msg = (
                "DesktopNotifier requires the desktop-notifier package; install it with "
                "'pip install watchtower[desktop]' or 'uv add watchtower[desktop]'."
            )
            raise MissingDependencyError(msg) from e
        raise NotImplementedError

    def send(self, event: ChangeEvent) -> None:
        """Show the event's summary and changes as one desktop notification.

        Args:
            event: Event to show.

        Raises:
            NotifyError: If the system cannot show the notification.
        """
        raise NotImplementedError
