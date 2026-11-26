"""Tests for PoliteTransport (spacing per host and revalidation of saved responses)."""

from __future__ import annotations

import gzip

import httpx
import pytest

from conftest import FakeListings
from watchtower.sources import PoliteTransport

_URL = "http://example.test/page"


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


def _replying(
    *responses: httpx.Response, min_delay: float = 0.0
) -> tuple[PoliteTransport, list[httpx.Request], _Clock]:
    """Build a PoliteTransport whose server sends `responses` in order and records requests."""
    sent: list[httpx.Request] = []
    clock = _Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return responses[len(sent) - 1]

    transport = PoliteTransport(
        httpx.MockTransport(handler),
        min_delay=min_delay,
        now=clock.fake_now,
        sleep=clock.fake_sleep,
    )
    return transport, sent, clock


def _get(transport: PoliteTransport, url: str = _URL) -> httpx.Response:
    """Send a GET for `url` through `transport` and read the body."""
    response = transport.handle_request(httpx.Request("GET", url))
    response.read()
    return response


def test_init_rejects_negative_min_delay() -> None:
    """A negative min_delay is rejected at construction time."""
    with pytest.raises(ValueError, match="min_delay must not be negative"):
        PoliteTransport(httpx.MockTransport(lambda _: _response()), min_delay=-0.5)


def test_first_request_is_sent_without_validators() -> None:
    """Nothing is saved yet, so the first request goes out unchanged."""
    transport, sent, _ = _replying(_response(200, "hello", {"etag": '"a"'}))

    assert _get(transport).text == "hello"
    assert "If-None-Match" not in sent[0].headers


def test_validators_of_a_saved_response_are_sent_back() -> None:
    """The next GET of the URL sends the saved ETag and Last-Modified."""
    validators = {"etag": '"a"', "last-modified": "Wed, 25 Nov 2026 10:00:00 GMT"}
    transport, sent, _ = _replying(_response(200, "hello", validators), _response(304))

    _get(transport)
    _get(transport)

    assert sent[1].headers["If-None-Match"] == '"a"'
    assert sent[1].headers["If-Modified-Since"] == "Wed, 25 Nov 2026 10:00:00 GMT"


def test_not_modified_returns_the_saved_response() -> None:
    """On a 304 the caller gets the saved 200 with its body."""
    transport, _, _ = _replying(_response(200, "hello", {"etag": '"a"'}), _response(304))

    _get(transport)
    second = _get(transport)

    assert second.status_code == 200
    assert second.text == "hello"
    assert second.headers["etag"] == '"a"'


def test_saved_compressed_response_is_replayed_decoded() -> None:
    """A gzip response is saved decoded, so replaying it does not decode it twice."""
    compressed = httpx.Response(
        200,
        content=gzip.compress(b"hello"),
        headers={"content-encoding": "gzip", "etag": '"a"'},
    )
    transport, _, _ = _replying(compressed, _response(304))

    assert _get(transport).text == "hello"
    assert _get(transport).text == "hello"


def test_new_200_replaces_the_saved_response() -> None:
    """A changed page is saved, and its ETag is sent next time."""
    transport, sent, _ = _replying(
        _response(200, "old", {"etag": '"a"'}),
        _response(200, "new", {"etag": '"b"'}),
        _response(304),
    )

    _get(transport)
    assert _get(transport).text == "new"
    assert _get(transport).text == "new"
    assert sent[2].headers["If-None-Match"] == '"b"'


def test_error_is_passed_through_and_keeps_the_saved_response() -> None:
    """A 404 reaches the caller, and a later 304 still replays the older copy."""
    transport, _, _ = _replying(
        _response(200, "hello", {"etag": '"a"'}), _response(404), _response(304)
    )

    _get(transport)
    assert _get(transport).status_code == 404
    assert _get(transport).text == "hello"


@pytest.mark.parametrize(
    "first",
    [
        _response(200, "hello"),
        _response(200, "hello", {"etag": '"a"', "cache-control": "no-store"}),
        _response(404, "missing", {"etag": '"a"'}),
    ],
    ids=["no validator", "no-store", "not 200"],
)
def test_response_that_cannot_be_saved_is_not_revalidated(first: httpx.Response) -> None:
    """Without a saved copy the next request is a plain GET again."""
    transport, sent, _ = _replying(first, _response(200, "hello"))

    _get(transport)
    _get(transport)

    assert "If-None-Match" not in sent[1].headers


def test_caller_request_is_left_untouched() -> None:
    """Validators are added to a copy, not to the request the caller passed."""
    transport, _, _ = _replying(_response(200, "hello", {"etag": '"a"'}), _response(304))
    _get(transport)
    request = httpx.Request("GET", _URL)

    transport.handle_request(request)

    assert "If-None-Match" not in request.headers


def test_requests_to_the_same_host_are_spaced() -> None:
    """The second request to a host waits for the rest of min_delay."""
    transport, _, clock = _replying(_response(), _response(), min_delay=1.0)

    _get(transport, "http://example.test/a")
    clock.now = 0.4
    _get(transport, "http://example.test/b")

    assert clock.sleeps == [0.6]


def test_requests_to_different_hosts_do_not_wait() -> None:
    """Different hosts never wait for each other."""
    transport, _, clock = _replying(_response(), _response(), min_delay=1.0)

    _get(transport, "http://example.test/a")
    _get(transport, "http://other.test/b")

    assert clock.sleeps == []


def test_zero_delay_never_sleeps() -> None:
    """A zero min_delay never sleeps, even between requests to the same host."""
    transport, _, clock = _replying(_response(), _response(), min_delay=0.0)

    _get(transport)
    _get(transport)

    assert clock.sleeps == []


@pytest.mark.network
def test_polite_revalidates_with_server_and_honors_304(fake_listings: FakeListings) -> None:
    """The real server answers the second request with 304 and the saved page is returned."""
    url = f"{fake_listings.base_url}/listings"
    inner = _CountingTransport(httpx.HTTPTransport())
    transport = PoliteTransport(inner, min_delay=0.0)

    try:
        first = _get(transport, url)
        second = _get(transport, url)
    finally:
        inner.close()

    assert inner.statuses == [200, 304]
    assert inner.requests[1].headers["If-None-Match"] == first.headers["etag"]
    assert second.status_code == 200
    assert second.content == first.content
