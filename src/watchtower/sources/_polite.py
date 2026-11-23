"""PoliteTransport limiting how often a website is asked (Proxy pattern)."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx


class PoliteTransport(httpx.BaseTransport):
    """Stands in for another transport: waits between requests and reuses unchanged responses."""

    def __init__(
        self,
        inner: httpx.BaseTransport,
        *,
        min_delay: float = 1.0,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize PoliteTransport.

        Args:
            inner: Transport that really sends the requests.
            min_delay: Seconds between two requests to the same domain.
            now: Function returning the current time in seconds; tests pass a fake one.
            sleep: Function that waits; tests pass a fake one.
        """
        raise NotImplementedError

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send a request, asking the server only whether a saved response has changed.

        Args:
            request: Request to send.

        Returns:
            The server's response, or the saved one if the server answers 304 Not Modified.

        Raises:
            httpx.TransportError: If the request cannot be sent.
        """
        raise NotImplementedError
