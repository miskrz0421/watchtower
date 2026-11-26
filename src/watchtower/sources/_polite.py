"""PoliteTransport limiting how often a website is asked (Proxy pattern)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

# Describe the body as sent on the wire; we store the already-decoded body instead,
# so these must not be replayed with it.
_BODY_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


@dataclass(frozen=True)
class _Saved:
    """An immutable copy of a response, safe to replay any number of times."""

    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    @classmethod
    def from_response(cls, response: httpx.Response) -> _Saved:
        """Read `response` completely, close it, and keep a copy.

        Args:
            response: Response to parse.

        Returns:
            The _Saved object parsed from the response.
        """
        try:
            body = response.read()
        finally:
            response.close()
        return cls(
            status_code=response.status_code,
            headers=tuple(
                (header, value)
                for header, value in response.headers.multi_items()
                if header.lower() not in _BODY_HEADERS
            ),
            body=body,
        )

    def to_response(self) -> httpx.Response:
        """Build a fresh response; callers can't affect the saved copy.

        Returns:
            A response built from the saved state.
        """
        return httpx.Response(
            self.status_code,
            headers=self.headers,
            content=self.body,
        )

    def validators(self) -> dict[str, str]:
        """Return the headers for a request matching this response.

        Returns:
            The matching headers.
        """
        response_headers = httpx.Headers(self.headers)
        request_headers: dict[str, str] = {}
        if etag := response_headers.get("etag"):
            request_headers["If-None-Match"] = etag
        if last_modified := response_headers.get("last-modified"):
            request_headers["If-Modified-Since"] = last_modified
        return request_headers


def _is_storable(response: httpx.Response) -> bool:
    """Check whether a response can be saved for revalidation.

    Args:
        response: Response to check.

    Returns:
        True for a 200 with an ETag or Last-Modified that does not forbid storing.
    """
    if response.status_code != 200:
        return False
    if "etag" not in response.headers and "last-modified" not in response.headers:
        return False
    return "no-store" not in response.headers.get("cache-control", "").lower()


def _with_headers(request: httpx.Request, extra: dict[str, str]) -> httpx.Request:
    """Copy `request` with extra headers, leaving the caller's request untouched.

    Args:
        request: Request to copy.
        extra: Headers to add to the copy.

    Returns:
        The new request.
    """
    headers = request.headers.copy()
    headers.update(extra)
    return httpx.Request(
        request.method,
        request.url,
        headers=headers,
        stream=request.stream,
        extensions=dict(request.extensions),
    )


class PoliteTransport(httpx.BaseTransport):
    """Stands in for another transport: waits between requests and reuses unchanged responses.

    One instance can be shared by several clients. It never closes `inner`, so whoever
    created `inner` is responsible for closing it.
    """

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

        Raises:
            ValueError: If min_delay is negative.
        """
        if min_delay < 0:
            raise ValueError("min_delay must not be negative")
        self._inner = inner
        self._min_delay = min_delay
        self._now = now
        self._sleep = sleep

        self._saved: dict[str, _Saved] = {}
        self._last_sent: dict[str, float] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send a request, asking the server only whether a saved response has changed.

        Args:
            request: Request to send.

        Returns:
            The server's response, or the saved one if the server answers 304 Not Modified.

        Raises:
            httpx.TransportError: If the request cannot be sent.
        """
        key = str(request.url)
        outgoing = request
        if saved := self._saved.get(key):
            outgoing = _with_headers(request, saved.validators())

        self._wait_for_turn(request.url.host)
        response = self._inner.handle_request(outgoing)

        if response.status_code == 304 and saved is not None:
            try:
                response.read()
            finally:
                response.close()
            return saved.to_response()

        if _is_storable(response):
            saved = _Saved.from_response(response)
            self._saved[key] = saved
            return saved.to_response()

        # Any other status (404, 500, ...) is passed through, keeping the saved copy.
        return response

    def _wait_for_turn(self, host: str) -> None:
        """Wait until `min_delay` has passed since the last request to `host`.

        Args:
            host: Domain of the request, without the port.
        """
        last = self._last_sent.get(host)
        if last is not None:
            remaining = self._min_delay - (self._now() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_sent[host] = self._now()
