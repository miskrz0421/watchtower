"""DiscordNotifier posting change events to a Discord channel."""

from __future__ import annotations

import httpx

from watchtower._errors import NotifyError
from watchtower._models import ChangeEvent
from watchtower._registry import register_notifier
from watchtower.notifiers._base import Notifier
from watchtower.notifiers._console import _change_text
from watchtower.sources._http import DEFAULT_TIMEOUT_SECONDS, USER_AGENT

# Discord webhooks reject messages longer than 2000 characters.
MAX_CONTENT_LENGTH = 2000


@register_notifier("discord")
class DiscordNotifier(Notifier):
    """Notifier posting each change event to a Discord webhook (see ADR-011)."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize DiscordNotifier.

        Args:
            webhook_url: The channel's webhook address. It is a secret, so the
                config writes `${DISCORD_WEBHOOK_URL}` (see ADR-010).
            timeout: Request timeout in seconds.
            transport: Optional transport; tests pass `httpx.MockTransport`.
        """
        self._webhook_url = webhook_url
        self._timeout = timeout
        self._transport = transport

    def send(self, event: ChangeEvent) -> None:
        """Post the event's summary and changes as one Discord message.

        Args:
            event: Event to post.

        Raises:
            NotifyError: If the webhook cannot be reached or rejects the message.
        """
        lines = [f"**{event.watcher_name}: {event.summary}**"]
        lines.extend(_change_text(change) for change in event.changes)
        message = "\n".join(lines)
        if len(message) > MAX_CONTENT_LENGTH:
            message = message[: MAX_CONTENT_LENGTH - 1] + "…"

        try:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.post(self._webhook_url, json={"content": message})
                response.raise_for_status()
        except httpx.HTTPError as e:
            # The webhook URL is a secret, so keep the error message generic.
            msg = "Could not send Discord notification."
            raise NotifyError(msg) from e
