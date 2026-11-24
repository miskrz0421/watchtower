"""DesktopNotifier showing change events as desktop notifications."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from watchtower._errors import MissingDependencyError, NotifyError
from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier
from watchtower.notifiers._format import change_text, truncate

# WinRT toast XML has a ~30 KB payload limit. Stay far below it: escaping can
# expand the text, and desktop popups truncate long messages visually anyway.
_MAX_MESSAGE_LENGTH = 2000


@runtime_checkable
class _NotificationBackend(Protocol):
    """The part of DesktopNotifierSync that DesktopNotifier uses."""

    def send(self, title: str, message: str) -> str:
        """Show a notification and return its identifier."""
        ...


@register_notifier("desktop")
class DesktopNotifier(Notifier):
    """Notifier showing each change event as a best-effort OS notification (see ADR-024)."""

    def __init__(self, *, backend: _NotificationBackend | None = None) -> None:
        """Initialize DesktopNotifier.

        Args:
            backend: Object with `send(title, message)`; tests pass a fake. None
                means the real `desktop-notifier` backend.

        Raises:
            MissingDependencyError: If no backend is given and the extra is missing.
        """
        if backend is None:
            # Imported here so `import watchtower` works without the extra (ADR-003).
            try:
                from desktop_notifier.sync import DesktopNotifierSync
            except ImportError as e:
                msg = (
                    "DesktopNotifier requires the desktop-notifier package; "
                    "install it with `uv sync --extra desktop`"
                )
                raise MissingDependencyError(msg) from e
            backend = DesktopNotifierSync(app_name="watchtower")
        self._backend = backend

    def send(self, event: ChangeEvent) -> None:
        """Show the event's summary and changes, cut to 2000 characters, as one notification.

        Args:
            event: Event to show.

        Raises:
            NotifyError: If the backend raises an error.
        """
        title = f"{event.watcher_name}: {event.summary}"
        message = "\n".join(change_text(change) for change in event.changes)
        message = truncate(message, _MAX_MESSAGE_LENGTH)
        try:
            self._backend.send(title, message)
        except Exception as e:
            # The real library logs delivery failures instead of raising; only
            # errors that actually escape the backend end up here.
            msg = "Cannot show desktop notification."
            raise NotifyError(msg) from e
