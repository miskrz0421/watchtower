"""Tests for HttpSource (offline mock tests and live network tests)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import httpx
import pytest

from conftest import FakeListings
from watchtower import Item, SourceError
from watchtower._http import USER_AGENT
from watchtower.sources import HttpSource, JSONAPISource, RSSSource, WebPageSource


class PlainHttpSource(HttpSource):
    """HttpSource that produces no items."""

    def parse(self, raw: str) -> Iterable[Item]:
        """Return no items."""
        return ()


def _webpage_source(base_url: str) -> WebPageSource:
    """Build a WebPageSource reading the server's listings page."""
    return WebPageSource(
        url=f"{base_url}/listings",
        selector=".offer",
        title_selector=".title",
        price_selector=".price",
        key_attribute="data-id",
    )


def _rss_source(base_url: str) -> RSSSource:
    """Build an RSSSource reading the server's feed."""
    return RSSSource(url=f"{base_url}/feed.xml")


def _json_api_source(base_url: str) -> JSONAPISource:
    """Build a JSONAPISource reading the server's JSON endpoint."""
    return JSONAPISource(
        url=f"{base_url}/listings.json", price_field="price", text_field="description"
    )


def test_http_source_returns_body_and_sends_user_agent() -> None:
    """Test that the response body becomes the snapshot's raw text."""
    seen_agents: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_agents.append(request.headers.get("User-Agent"))
        return httpx.Response(200, text="hello")

    source = PlainHttpSource("http://test/page", transport=httpx.MockTransport(handler))

    assert source.snapshot().raw_text == "hello"
    assert seen_agents == [USER_AGENT]


def test_http_source_error_status_raises_source_error() -> None:
    """Test that an HTTP error status is reported as SourceError."""
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    source = PlainHttpSource("http://test/page", transport=transport)

    with pytest.raises(SourceError):
        source.snapshot()


@pytest.mark.network
def test_sources_agree_on_the_same_listings(fake_listings: FakeListings) -> None:
    """Test that the three renderings of one dataset yield the same Items."""
    webpage = _webpage_source(fake_listings.base_url).snapshot().items
    rss = _rss_source(fake_listings.base_url).snapshot().items
    json_api = _json_api_source(fake_listings.base_url).snapshot().items

    for other in (rss, json_api):
        assert [item.key for item in other] == [item.key for item in webpage]
        assert [item.title for item in other] == [item.title for item in webpage]
        assert [item.price for item in other] == [item.price for item in webpage]


@pytest.mark.network
@pytest.mark.parametrize(
    "build",
    [_webpage_source, _rss_source, _json_api_source],
    ids=["webpage", "rss", "json_api"],
)
def test_sources_report_broken_server_data_as_source_error(
    fake_listings: FakeListings, build: Callable[[str], HttpSource]
) -> None:
    """Test that a server answering 500 to a broken data file is a SourceError."""
    fake_listings.data_path.write_text("[{broken", encoding="utf-8")

    with pytest.raises(SourceError):
        build(fake_listings.base_url).snapshot()
