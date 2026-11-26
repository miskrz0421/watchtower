"""PoliteTransport limiting how often a website is asked (Proxy pattern)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import httpx

# Describe the body as sent on the wire; we store the already-decoded body instead,
# so these must not be replayed with it.
_BODY_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})

# If the caller sends any of these, they are doing their own conditional request and
# must see the server's answer (including a 304) untouched.
_CALLER_CONDITIONALS = (
    "if-none-match",
    "if-modified-since",
    "if-match",
    "if-unmodified-since",
    "if-range",
)


@dataclass(frozen=True)
class _Saved:
    """An immutable copy of a response, safe to replay any number of times."""

    status_code: int
    headers: tuple[tuple[str, str], ...]  # without _BODY_HEADERS
    body: bytes  # decoded
    extensions: dict[str, Any]

    @classmethod
    def from_response(cls, response: httpx.Response) -> _Saved:
        """Read `response` completely, close it, and keep a copy."""
        try:
            body = response.read()
        finally:
            response.close()
        return cls(
            status_code=response.status_code,
            headers=tuple(
                (k, v) for k, v in response.headers.multi_items() if k.lower() not in _BODY_HEADERS
            ),
            body=body,
            extensions={
                k: v
                for k, v in response.extensions.items()
                if k in ("http_version", "reason_phrase")
            },
        )

    def to_response(self) -> httpx.Response:
        """Build a fresh response; callers can't affect the saved copy."""
        return httpx.Response(
            self.status_code,
            headers=self.headers,
            content=self.body,
            extensions=dict(self.extensions),
        )

    def validators(self) -> dict[str, str]:
        """Return the conditional request headers matching this response."""
        headers = httpx.Headers(self.headers)
        out: dict[str, str] = {}
        if etag := headers.get("etag"):
            out["If-None-Match"] = etag
        if last_modified := headers.get("last-modified"):
            out["If-Modified-Since"] = last_modified
        return out

    def refreshed_by(self, not_modified: httpx.Response) -> _Saved:
        """Return a copy that adopts any new validators sent with a 304."""
        headers = httpx.Headers(self.headers)
        for name in ("etag", "last-modified"):
            if name in not_modified.headers:
                headers[name] = not_modified.headers[name]
        return replace(self, headers=tuple(headers.multi_items()))


def _is_storable(response: httpx.Response) -> bool:
    """A 200 that offers a validator and doesn't forbid storing."""
    if response.status_code != 200:
        return False
    if "etag" not in response.headers and "last-modified" not in response.headers:
        return False
    return "no-store" not in response.headers.get("cache-control", "").lower()


def _with_headers(request: httpx.Request, extra: dict[str, str]) -> httpx.Request:
    """Copy `request` with extra headers, leaving the caller's request untouched."""
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
        """
        if min_delay < 0:
            raise ValueError("min_delay must not be negative")
        self._inner = inner
        self._min_delay = min_delay
        self._now = now
        self._sleep = sleep

        self._guard = threading.Lock()  # protects the two dicts below
        self._host_locks: dict[str, threading.Lock] = {}
        self._saved: dict[str, _Saved] = {}
        self._last_sent: dict[str, float] = {}  # each entry guarded by its host lock

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send a request, asking the server only whether a saved response has changed.

        Args:
            request: Request to send.

        Returns:
            The server's response, or the saved one if the server answers 304 Not Modified.

        Raises:
            httpx.TransportError: If the request cannot be sent.
        """
        # Only plain GETs are saved and revalidated.
        revalidate = request.method == "GET" and not any(
            name in request.headers for name in _CALLER_CONDITIONALS
        )
        key = str(request.url)

        saved = None
        outgoing = request
        if revalidate:
            with self._guard:
                saved = self._saved.get(key)
            if saved is not None:
                outgoing = _with_headers(request, saved.validators())

        self._wait_for_turn(request.url.host)
        response = self._inner.handle_request(outgoing)

        if not revalidate:
            return response

        if response.status_code == 304 and saved is not None:
            try:
                response.read()
            finally:
                response.close()
            saved = saved.refreshed_by(response)
            with self._guard:
                self._saved[key] = saved
            return saved.to_response()

        if response.status_code == 200:
            if _is_storable(response):
                saved = _Saved.from_response(response)
                with self._guard:
                    self._saved[key] = saved
                return saved.to_response()
            # The resource no longer offers validators; the old copy is useless.
            with self._guard:
                self._saved.pop(key, None)

        # Any other status (404, 500, ...) is passed through, keeping the saved copy.
        return response

    def _wait_for_turn(self, host: str) -> None:
        """Block until `min_delay` has passed since the last request to `host`.

        Spacing is measured between request start times. Threads sending to the
        same host queue up here; different hosts never wait for each other.
        """
        with self._guard:
            lock = self._host_locks.setdefault(host, threading.Lock())
        with lock:
            last = self._last_sent.get(host)
            if last is not None:
                remaining = self._min_delay - (self._now() - last)
                if remaining > 0:
                    self._sleep(remaining)
            self._last_sent[host] = self._now()
