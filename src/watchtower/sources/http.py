"""Base class for sources that download their content over HTTP."""

from __future__ import annotations

import httpx

from watchtower.sources.base import Source

DEFAULT_TIMEOUT_SECONDS = 10.0
USER_AGENT = "Watchtower/0.1"


class HttpSource(Source):
    """Source that downloads text from a URL.

    Subclasses only implement `parse()`. Errors raised here are converted to
    `SourceError` by the `snapshot()` template method.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize HttpSource.

        Args:
            url: Address to download.
            timeout: Request timeout in seconds.
            transport: Optional transport; tests pass `httpx.MockTransport`
                so that they never touch the network.
        """
        self.url = url
        self._timeout = timeout
        self._transport = transport

    def fetch(self) -> str:
        """Download the URL and return the response body as text.

        Returns:
            Decoded response body.

        Raises:
            httpx.HTTPError: If the request fails or the status is an error.
        """
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=True,
        ) as client:
            response = client.get(self.url)
            response.raise_for_status()
            return response.text
