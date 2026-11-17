"""DiscordNotifier posting change events to a Discord channel."""

from __future__ import annotations

import httpx

from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier


@register_notifier("discord")
class DiscordNotifier(Notifier):
    """Notifier posting each change event to a Discord webhook (see ADR-011)."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize DiscordNotifier.

        Args:
            webhook_url: The channel's webhook address. It is a secret, so the
                config writes `${DISCORD_WEBHOOK_URL}` (see ADR-010).
            timeout: Request timeout in seconds.
            transport: Optional transport; tests pass `httpx.MockTransport`.
        """
        raise NotImplementedError

    def send(self, event: ChangeEvent) -> None:
        """Post the event's summary and changes as one Discord message.

        Args:
            event: Event to post.

        Raises:
            NotifyError: If the webhook cannot be reached or rejects the message.
        """
        raise NotImplementedError
