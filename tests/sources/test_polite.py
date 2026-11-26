"""Tests for PoliteTransport (polite inter-request spacing + revalidation cache)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from conftest import FakeListings
from watchtower.sources._polite import (
    PoliteTransport,
    _is_storable,
    _Saved,
    _with_headers,
)


def _request(
    method: str = "GET",
    url: str = "http://example.test/",
    headers: dict[str, str] | None = None,
) -> httpx.Request:
    """Build an httpx request for the given method, URL and optional headers."""
    return httpx.Request(method, url, headers=headers)


def _response(
    status: int = 200, text: str = "", headers: dict[str, str] | None = None
) -> httpx.Response:
    """Build an httpx response with the given status, text and headers."""
    return httpx.Response(status, text=text, headers=headers or {})


class _Clock:
    """Fake controllable clock paired with a sleep recorder."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def fake_now(self) -> float:
        """Return the fake current time."""
        return self.now

    def fake_sleep(self, seconds: float) -> None:
        """Record a sleep instead of really waiting, advancing the fake clock."""
        self.sleeps.append(seconds)
        self.now += seconds


class _CountingTransport(httpx.BaseTransport):
    """Wrap a transport and record the requests and statuses it exchanges."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        """Remember the wrapped transport and start with empty records."""
        self._inner = inner
        self.requests: list[httpx.Request] = []
        self.statuses: list[int] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request and its status, then return the wrapped response."""
        self.requests.append(request)
        response = self._inner.handle_request(request)
        self.statuses.append(response.status_code)
        return response

    def close(self) -> None:
        """Close the wrapped transport."""
        self._inner.close()


def _make_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    min_delay: float = 1.0,
    clock: _Clock | None = None,
) -> tuple[PoliteTransport, _Clock]:
    """Build a PoliteTransport wrapping a MockTransport with a fake clock."""
    clock = clock or _Clock()
    inner = httpx.MockTransport(handler)
    transport = PoliteTransport(
        inner, min_delay=min_delay, now=clock.fake_now, sleep=clock.fake_sleep
    )
    return transport, clock


def test_saved_from_response_filters_body_headers() -> None:
    """from_response keeps the decoded body and drops body/transport headers."""
    response = _response(200, text="body", headers={"etag": '"abc"', "content-length": "4"})

    saved = _Saved.from_response(response)

    assert saved.status_code == 200
    assert saved.body == b"body"
    # content-length is a body header, so it must not be stored.
    assert dict(saved.headers) == {"etag": '"abc"', "content-type": "text/plain; charset=utf-8"}


def test_saved_to_response_returns_equivalent_response() -> None:
    """to_response builds a fresh response equivalent to the saved copy."""
    saved = _Saved(200, (("etag", '"abc"'),), b"body")

    response = saved.to_response()

    assert response.status_code == 200
    assert response.read() == b"body"
    assert response.headers.get("etag") == '"abc"'


def test_saved_validators_returns_etag_and_last_modified() -> None:
    """Validators returns the conditional headers matching a saved response."""
    saved = _Saved(200, (("etag", '"abc"'), ("last-modified", "Wed")), b"body")

    assert saved.validators() == {"If-None-Match": '"abc"', "If-Modified-Since": "Wed"}


def test_saved_validators_omits_missing_headers() -> None:
    """Validators omits validators that the saved response does not have."""
    saved = _Saved(200, (("etag", '"abc"'),), b"body")

    assert saved.validators() == {"If-None-Match": '"abc"'}


def test_is_storable_true_for_200_with_validator() -> None:
    """A 200 with a validator is storable."""
    assert _is_storable(_response(200, headers={"etag": '"a"'})) is True


def test_is_storable_true_when_cache_control_allows_storing() -> None:
    """cache-control without no-store keeps the response storable."""
    response = _response(200, headers={"etag": '"a"', "cache-control": "public"})
    assert _is_storable(response) is True


@pytest.mark.parametrize("status", [201, 304, 404, 500])
def test_is_storable_false_for_non_200(status: int) -> None:
    """Only a 200 is storable; every other status is not."""
    assert _is_storable(_response(status, headers={"etag": '"a"'})) is False


def test_is_storable_false_without_validator() -> None:
    """A 200 without etag/last-modified is not storable."""
    assert _is_storable(_response(200)) is False


def test_is_storable_false_for_no_store() -> None:
    """A 200 with cache-control: no-store is not storable."""
    response = _response(200, headers={"etag": '"a"', "cache-control": "no-store"})
    assert _is_storable(response) is False


def test_with_headers_returns_copy_with_extra_headers_and_leaves_caller_untouched() -> None:
    """_with_headers adds headers to a copy without touching the caller's request."""
    request = _request(headers={"accept": "text/html"})
    outgoing = _with_headers(request, {"x-extra": "1"})

    assert outgoing.headers.get("accept") == "text/html"
    assert outgoing.headers.get("x-extra") == "1"
    assert "x-extra" not in request.headers


def test_with_headers_does_not_share_extensions_dict() -> None:
    """Regression test: the outgoing request gets its own extensions dict."""
    request = _request()
    request.extensions["caller"] = "value"
    outgoing = _with_headers(request, {"x-extra": "1"})

    assert outgoing.extensions is not request.extensions
    outgoing.extensions["added-by-inner"] = "2"
    assert "added-by-inner" not in request.extensions


def test_init_rejects_negative_min_delay() -> None:
    """A negative min_delay is rejected at construction time."""
    with pytest.raises(ValueError, match="min_delay must not be negative"):
        PoliteTransport(httpx.MockTransport(lambda _: _response()), min_delay=-0.5)


def test_handle_request_get_sends_and_caches_storable_response() -> None:
    """A first GET is forwarded, and a storable 200 is cached for revalidation."""
    clock = _Clock()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _response(200, text="hello", headers={"etag": '"a"'})

    transport, _ = _make_transport(handler, clock=clock)

    request = _request("GET", "http://example.test/page")
    first = transport.handle_request(request)

    assert first.status_code == 200
    assert first.read() == b"hello"
    # Nothing saved yet, so no revalidation headers are added.
    assert "If-None-Match" not in seen[0].headers

    second = transport.handle_request(request)
    assert second.read() == b"hello"
    # The cached validator is used on the next request to the same URL.
    assert seen[1].headers.get("If-None-Match") == '"a"'


def test_handle_request_post_is_not_revalidated_or_cached() -> None:
    """Non-GET requests are forwarded as-is and never cached."""
    clock = _Clock()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _response(200, text="posted")

    transport, _ = _make_transport(handler, clock=clock)

    request = _request("POST", "http://example.test/page")
    first = transport.handle_request(request)
    second = transport.handle_request(request)

    assert first.status_code == 200
    assert first.read() == b"posted"
    assert second.read() == b"posted"
    # Both POSTs were forwarded without revalidation headers.
    assert len(seen) == 2
    assert all("If-None-Match" not in sent.headers for sent in seen)


def test_handle_request_get_with_caller_conditional_is_not_revalidated() -> None:
    """A GET carrying the caller's own conditionals is forwarded untouched."""
    clock = _Clock()
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("If-None-Match"))
        return _response(200, text="ok")

    transport, _ = _make_transport(handler, clock=clock)

    request = _request("GET", "http://example.test/page", headers={"If-None-Match": '"caller"'})
    first = transport.handle_request(request)
    second = transport.handle_request(request)

    assert first.status_code == 200
    assert second.read() == b"ok"
    # Both requests still carry exactly the caller's conditional.
    assert seen == ['"caller"', '"caller"']


def test_handle_request_get_with_saved_200_stores_new_response() -> None:
    """A fresh 200 replaces the saved copy for the same URL."""
    clock = _Clock()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return _response(200, text="old", headers={"etag": '"a"'})
        return _response(200, text="updated", headers={"etag": '"b"'})

    transport, _ = _make_transport(handler, clock=clock)

    request = _request("GET", "http://example.test/page")
    first = transport.handle_request(request)
    second = transport.handle_request(request)
    third = transport.handle_request(request)

    assert first.read() == b"old"
    assert second.status_code == 200
    assert second.read() == b"updated"
    assert seen[1].headers.get("If-None-Match") == '"a"'
    # The third request revalidates against the newly saved response.
    assert third.read() == b"updated"
    assert seen[2].headers.get("If-None-Match") == '"b"'


def test_handle_request_get_with_saved_404_keeps_saved_and_passes_through() -> None:
    """A 404 is passed through while the saved copy is kept intact."""
    clock = _Clock()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return _response(200, text="hello", headers={"etag": '"a"'})
        if len(seen) == 2:
            return _response(404)
        return _response(304)

    transport, _ = _make_transport(handler, clock=clock)

    request = _request("GET", "http://example.test/page")
    first = transport.handle_request(request)
    missing = transport.handle_request(request)
    third = transport.handle_request(request)

    assert first.read() == b"hello"
    assert missing.status_code == 404
    assert seen[1].headers.get("If-None-Match") == '"a"'
    # The 304 still replays the copy saved before the 404.
    assert third.status_code == 200
    assert third.read() == b"hello"


def test_handle_request_revalidation_does_not_share_extensions_with_caller_request() -> None:
    """Regression test: revalidation via _with_headers does not share extensions."""
    clock = _Clock()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return _response(200, text="old", headers={"etag": '"old"'})
        # The inner transport mutates its own extensions copy only.
        request.extensions["inner"] = "added"
        return _response(200, text="fresh", headers={"etag": '"b"'})

    transport, _ = _make_transport(handler, clock=clock)

    request = _request("GET", "http://example.test/page")
    request.extensions["caller"] = "value"
    first = transport.handle_request(request)
    second = transport.handle_request(request)

    assert first.read() == b"old"
    assert second.status_code == 200
    assert second.read() == b"fresh"
    assert seen[1].headers.get("If-None-Match") == '"old"'
    # Revalidation used a copy, so the caller's extensions dict is untouched.
    assert "inner" not in request.extensions


def test_wait_spaces_requests_to_the_same_host() -> None:
    """Requests to the same host are spaced by min_delay."""
    clock = _Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=1.0, clock=clock)

    transport.handle_request(_request("GET", "http://example.test/a"))
    assert clock.sleeps == []

    clock.now = 0.4
    transport.handle_request(_request("GET", "http://example.test/b"))
    assert clock.sleeps == [0.6]  # 1.0 - (0.4 - 0.0)


def test_wait_does_not_delay_different_hosts() -> None:
    """Requests to different hosts never wait for each other."""
    clock = _Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=1.0, clock=clock)

    transport.handle_request(_request("GET", "http://example.test/a"))
    transport.handle_request(_request("GET", "http://other.test/b"))
    assert clock.sleeps == []


def test_wait_zero_delay_never_sleeps() -> None:
    """A zero min_delay never sleeps, even between requests to the same host."""
    clock = _Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=0.0, clock=clock)

    transport.handle_request(_request("GET", "http://example.test/a"))
    clock.now = 0.0
    transport.handle_request(_request("GET", "http://example.test/b"))
    assert clock.sleeps == []


@pytest.mark.network
def test_polite_spaces_real_requests_to_same_host(fake_listings: FakeListings) -> None:
    """Test that PoliteTransport spaces real requests to the same host."""
    url = f"{fake_listings.base_url}/listings"
    clock = _Clock()
    inner = _CountingTransport(httpx.HTTPTransport())
    transport = PoliteTransport(inner, min_delay=0.1, now=clock.fake_now, sleep=clock.fake_sleep)

    try:
        transport.handle_request(_request("GET", url))
        transport.handle_request(_request("GET", url))
    finally:
        inner.close()

    # The second request had to wait one full min_delay; no real time passed.
    assert clock.sleeps == [0.1]
    assert len(inner.requests) == 2


@pytest.mark.network
def test_polite_revalidates_with_server_and_honors_304(fake_listings: FakeListings) -> None:
    """Test that PoliteTransport sends If-None-Match and returns the saved copy on 304."""
    url = f"{fake_listings.base_url}/listings"
    clock = _Clock()
    inner = _CountingTransport(httpx.HTTPTransport())
    transport = PoliteTransport(inner, min_delay=0.0, now=clock.fake_now, sleep=clock.fake_sleep)

    try:
        # First request: no saved copy, plain GET, server answers 200.
        first = transport.handle_request(_request("GET", url))
        assert first.status_code == 200
        first_body = first.read()

        # Second request: saved copy exists, so If-None-Match is sent.
        second = transport.handle_request(_request("GET", url))
        assert second.status_code == 200
        assert second.read() == first_body

        # The second request revalidated with the server, which answered 304.
        assert inner.statuses == [200, 304]
        assert inner.requests[1].headers.get("If-None-Match") == first.headers["etag"]
    finally:
        inner.close()
