"""DesktopNotifier showing change events as desktop notifications."""

from __future__ import annotations

from typing import Protocol

from watchtower._errors import MissingDependencyError, NotifyError
from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier
from watchtower.notifiers._format import change_text, truncate

# WinRT toast XML has a ~30 KB payload limit. Stay far below it: escaping can
# expand the text, and desktop popups truncate long messages visually anyway.
_MAX_MESSAGE_LENGTH = 2000


class _NotificationBackend(Protocol):
    """The part of DesktopNotifierSync that DesktopNotifier uses."""

    def send(self, title: str, message: str) -> str:
        """Show a notification and return its identifier."""
        ...


@register_notifier("desktop")
class DesktopNotifier(Notifier):
    """Notifier showing each change event as a notification of the operating system.

    Uses the `desktop-notifier` package, not Qt, so it works in `watchtower run`
    as well as in the tray app (see ADR-024).

    Delivery is best-effort. `desktop-notifier` catches delivery errors itself,
    logs a warning with a traceback and still returns a notification identifier;
    for example, KDE can reject a burst of similar notifications with a DBus
    error. Those failures do not reach `send()`. `NotifyError` only wraps an
    exception that actually propagates out of the backend, such as a setup
    error or a failure raised by a test fake.

    The OS notification server owns each notification's lifetime. A one-shot
    `watchtower check` exits immediately, so the notification may be removed
    as soon as it appears; use a long-running mode for lasting visibility.
    """

    def __init__(self, *, backend: _NotificationBackend | None = None) -> None:
        """Initialize DesktopNotifier.

        The optional package is imported here, not at module import time, so
        `import watchtower` works in a headless install (see ADR-003).

        Args:
            backend: Object with send(title, message); tests pass a fake. When
                None, the real backend is created from the optional extra.

        Raises:
            MissingDependencyError: If no backend was injected and the extra is missing.
        """
        if backend is None:
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
        """Show the event's summary and changes as one desktop notification.

        The message is truncated to max 2000 characters because of notification payload limits.

        Args:
            event: Event to show.

        Raises:
            NotifyError: If there is a problem with the backend.
                `desktop-notifier` does not raise when scheduling fails,
                it only logs a warning with a traceback.
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
