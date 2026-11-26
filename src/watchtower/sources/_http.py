"""Base class for sources that download their content over HTTP."""

from __future__ import annotations

import httpx

from watchtower._http import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from watchtower._retry import retry, timed
from watchtower.sources._base import Source
from watchtower.sources._polite import PoliteTransport

_SHARED_TRANSPORT = PoliteTransport(httpx.HTTPTransport())


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
        self._transport = transport if transport is not None else _SHARED_TRANSPORT

    @timed
    @retry(on=httpx.TransportError, times=3, first_delay=0.25)
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
