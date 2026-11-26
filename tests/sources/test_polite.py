"""Tests for PoliteTransport (polite inter-request spacing + revalidation cache)."""

from __future__ import annotations

import contextlib
import threading
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
    url: str = "http://example.com/",
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


# --------------------------------------------------------------------------- #
# _Saved
# --------------------------------------------------------------------------- #


def test_saved_from_response_filters_body_headers_and_extensions() -> None:
    """from_response keeps the decoded body and drops body/transport headers."""
    response = _response(200, text="body", headers={"etag": '"abc"', "content-length": "4"})
    response.extensions["http_version"] = "HTTP/1.1"
    response.extensions["internal"] = "secret"

    saved = _Saved.from_response(response)

    assert saved.status_code == 200
    assert saved.body == b"body"
    # content-length is a body header, so it must not be stored.
    assert dict(saved.headers) == {"etag": '"abc"', "content-type": "text/plain; charset=utf-8"}
    assert saved.extensions == {"http_version": "HTTP/1.1"}


def test_saved_to_response_returns_equivalent_response() -> None:
    """to_response builds a fresh response equivalent to the saved copy."""
    saved = _Saved(200, (("etag", '"abc"'),), b"body", {"http_version": "HTTP/1.1"})

    response = saved.to_response()

    assert response.status_code == 200
    assert response.read() == b"body"
    assert response.headers.get("etag") == '"abc"'


def test_saved_validators_returns_etag_and_last_modified() -> None:
    """Validators returns the conditional headers matching a saved response."""
    saved = _Saved(200, (("etag", '"abc"'), ("last-modified", "Wed")), b"body", {})

    assert saved.validators() == {"If-None-Match": '"abc"', "If-Modified-Since": "Wed"}


def test_saved_validators_omits_missing_headers() -> None:
    """Validators omits validators that the saved response does not have."""
    saved = _Saved(200, (("etag", '"abc"'),), b"body", {})

    assert saved.validators() == {"If-None-Match": '"abc"'}


def test_saved_refreshed_by_adopts_304_validators_without_mutating_original() -> None:
    """refreshed_by adopts validators from a 304 and leaves the original intact."""
    saved = _Saved(200, (("etag", '"old"'),), b"body", {})
    not_modified = _response(304, headers={"etag": '"new"', "last-modified": "Thu"})

    refreshed = saved.refreshed_by(not_modified)

    assert refreshed.headers == (("etag", '"new"'), ("last-modified", "Thu"))
    assert saved.headers == (("etag", '"old"'),)


# --------------------------------------------------------------------------- #
# _is_storable
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# _with_headers
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# PoliteTransport.__init__
# --------------------------------------------------------------------------- #


def test_init_rejects_negative_min_delay() -> None:
    """A negative min_delay is rejected at construction time."""
    with pytest.raises(ValueError, match="min_delay must not be negative"):
        PoliteTransport(httpx.MockTransport(lambda _: _response()), min_delay=-0.5)


def test_init_stores_settings() -> None:
    """__init__ stores inner transport, min_delay, now and sleep as given."""
    clock = _Clock()
    inner = httpx.MockTransport(lambda _: _response())
    now_fn = clock.fake_now
    sleep_fn = clock.fake_sleep
    transport = PoliteTransport(inner, min_delay=2.5, now=now_fn, sleep=sleep_fn)

    assert transport._inner is inner
    assert transport._min_delay == 2.5
    assert transport._now is now_fn
    assert transport._sleep is sleep_fn


# --------------------------------------------------------------------------- #
# PoliteTransport.handle_request
# --------------------------------------------------------------------------- #


def test_handle_request_get_sends_and_caches_storable_response() -> None:
    """A first GET is forwarded, and a storable 200 is cached for revalidation."""
    clock = _Clock()
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return _response(200, text="hello", headers={"etag": '"a"'})

    transport, _ = _make_transport(handler, clock=clock)

    req = _request("GET", "http://example.com/page")
    response = transport.handle_request(req)

    assert response.status_code == 200
    assert response.read() == b"hello"
    assert len(seen) == 1
    # Nothing saved yet, so no revalidation headers are added.
    assert "If-None-Match" not in seen[0].headers
    assert str(req.url) in transport._saved


def test_handle_request_post_is_not_revalidated_or_cached() -> None:
    """Non-GET requests are forwarded as-is and never cached."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        assert "If-None-Match" not in req.headers
        return _response(200, text="posted")

    transport, _ = _make_transport(handler, clock=clock)

    req = _request("POST", "http://example.com/page")
    response = transport.handle_request(req)

    assert response.status_code == 200
    assert response.read() == b"posted"
    assert transport._saved == {}


def test_handle_request_get_with_caller_conditional_is_not_revalidated() -> None:
    """A GET carrying the caller's own conditionals is forwarded untouched."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(200, text="ok")

    transport, _ = _make_transport(handler, clock=clock)

    req = _request("GET", "http://example.com/page", headers={"If-None-Match": '"caller"'})
    response = transport.handle_request(req)

    assert response.status_code == 200
    # Caller-owned conditionals are never cached or revalidated by the transport.
    assert transport._saved == {}


def test_handle_request_get_with_saved_304_returns_refreshed_saved_copy() -> None:
    """On a 304, the saved copy is refreshed with the 304's validators and returned."""
    clock = _Clock()
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return _response(304, headers={"etag": '"new"', "last-modified": "Thu"})

    transport, _ = _make_transport(handler, clock=clock)

    key = "http://example.com/page"
    transport._saved[key] = _Saved(200, (("etag", '"old"'),), b"old body", {})

    req = _request("GET", key)
    response = transport.handle_request(req)

    assert response.status_code == 200
    assert response.read() == b"old body"
    # The request carried the old validators.
    assert calls[0].headers.get("If-None-Match") == '"old"'
    # Validators were adopted from the 304.
    assert transport._saved[key].headers == (
        ("etag", '"new"'),
        ("last-modified", "Thu"),
    )


def test_handle_request_get_with_saved_200_stores_new_response() -> None:
    """A fresh 200 replaces the saved copy for the same URL."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(200, text="updated", headers={"etag": '"b"'})

    transport, _ = _make_transport(handler, clock=clock)

    key = "http://example.com/page"
    transport._saved[key] = _Saved(200, (("etag", '"old"'),), b"old", {})

    req = _request("GET", key)
    response = transport.handle_request(req)

    assert response.status_code == 200
    assert response.read() == b"updated"
    assert transport._saved[key].body == b"updated"


def test_handle_request_get_with_saved_200_without_validator_pops_saved() -> None:
    """A 200 without validators drops the stale saved copy."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(200, text="no validator")

    transport, _ = _make_transport(handler, clock=clock)

    key = "http://example.com/page"
    transport._saved[key] = _Saved(200, (("etag", '"old"'),), b"old", {})

    req = _request("GET", key)
    response = transport.handle_request(req)

    assert response.status_code == 200
    assert response.read() == b"no validator"
    assert key not in transport._saved


def test_handle_request_get_with_saved_404_keeps_saved_and_passes_through() -> None:
    """A 404 is passed through while the saved copy is kept intact."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(404)

    transport, _ = _make_transport(handler, clock=clock)

    key = "http://example.com/page"
    transport._saved[key] = _Saved(200, (("etag", '"old"'),), b"old", {})

    req = _request("GET", key)
    response = transport.handle_request(req)

    assert response.status_code == 404
    assert key in transport._saved


def test_handle_request_revalidation_does_not_share_extensions_with_caller_request() -> None:
    """Regression test: revalidation via _with_headers does not share extensions."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        # The inner transport mutates its own extensions copy only.
        req.extensions["inner"] = "added"
        return _response(200, text="fresh", headers={"etag": '"b"'})

    transport, _ = _make_transport(handler, clock=clock)

    key = "http://example.com/page"
    transport._saved[key] = _Saved(200, (("etag", '"old"'),), b"old", {})

    req = _request("GET", key)
    req.extensions["caller"] = "value"
    response = transport.handle_request(req)

    assert response.status_code == 200
    assert response.read() == b"fresh"
    # A saved entry exists, so _with_headers copied the request (with its own
    # extensions dict); the caller's dict is untouched.
    assert "inner" not in req.extensions


# --------------------------------------------------------------------------- #
# PoliteTransport._wait_for_turn (spacing)
# --------------------------------------------------------------------------- #


def test_wait_spaces_requests_to_the_same_host() -> None:
    """Requests to the same host are spaced by min_delay."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=1.0, clock=clock)

    transport.handle_request(_request("GET", "http://example.com/a"))
    assert clock.sleeps == []

    clock.now = 0.4
    transport.handle_request(_request("GET", "http://example.com/b"))
    assert clock.sleeps == [0.6]  # 1.0 - (0.4 - 0.0)


def test_wait_does_not_delay_different_hosts() -> None:
    """Requests to different hosts never wait for each other."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=1.0, clock=clock)

    transport.handle_request(_request("GET", "http://example.com/a"))
    transport.handle_request(_request("GET", "http://other.com/b"))
    assert clock.sleeps == []


def test_wait_zero_delay_never_sleeps() -> None:
    """A zero min_delay never sleeps, even between requests to the same host."""
    clock = _Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=0.0, clock=clock)

    transport.handle_request(_request("GET", "http://example.com/a"))
    clock.now = 0.0
    transport.handle_request(_request("GET", "http://example.com/b"))
    assert clock.sleeps == []


def test_concurrent_same_host_requests_are_serialized_by_host_lock() -> None:
    """Concurrent requests to the same host are serialized by the per-host lock."""
    clock = _Clock()
    barrier = threading.Barrier(5)

    def handler(req: httpx.Request) -> httpx.Response:
        barrier.wait()  # all arrive together, then contend on the host lock
        return _response(200)

    transport, _ = _make_transport(handler, min_delay=1.0, clock=clock)

    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            transport.handle_request(_request("GET", f"http://example.com/{index}"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    # First request needs no wait; the other four each wait one full delay.
    assert clock.sleeps == [1.0, 1.0, 1.0, 1.0]


# --------------------------------------------------------------------------- #
# PoliteTransport against the real fake_listings server
# --------------------------------------------------------------------------- #


@pytest.mark.network
def test_polite_spaces_real_requests_to_same_host(fake_listings: FakeListings) -> None:
    """Test that PoliteTransport spaces real requests to the same host."""
    url = f"{fake_listings.base_url}/listings"
    clock = _Clock()
    inner = httpx.HTTPTransport()
    transport = PoliteTransport(inner, min_delay=0.1, now=clock.fake_now, sleep=clock.fake_sleep)

    try:
        transport.handle_request(_request("GET", url))
        transport.handle_request(_request("GET", url))
    finally:
        inner.close()

    # The second request had to wait one full min_delay; no real time passed.
    assert clock.sleeps == [0.1]
    times = fake_listings.request_times("/listings")
    assert len(times) == 2


@pytest.mark.network
def test_polite_revalidates_with_server_and_honors_304(fake_listings: FakeListings) -> None:
    """Test that PoliteTransport sends If-None-Match and returns the saved copy on 304."""
    url = f"{fake_listings.base_url}/listings"
    clock = _Clock()
    inner = httpx.HTTPTransport()
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

        # Only two requests reached the server: one 200, one 304.
        assert fake_listings.request_count("/listings") == 2
    finally:
        inner.close()


@pytest.mark.network
def test_polite_does_not_delay_different_hosts(fake_listings: FakeListings) -> None:
    """Test that requests to different hosts are not spaced by PoliteTransport."""
    url = f"{fake_listings.base_url}/listings"
    clock = _Clock()
    inner = httpx.HTTPTransport()
    transport = PoliteTransport(inner, min_delay=1.0, now=clock.fake_now, sleep=clock.fake_sleep)

    try:
        transport.handle_request(_request("GET", url))
        with contextlib.suppress(httpx.ConnectError):
            transport.handle_request(_request("GET", "http://example.com/"))
    finally:
        inner.close()

    # Only one request went to the fake server, and different hosts never wait.
    assert fake_listings.request_count("/listings") == 1
    assert clock.sleeps == []
