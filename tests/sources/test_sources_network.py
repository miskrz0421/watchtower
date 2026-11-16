"""Network tests for HttpSource subclasses against the local fake listings server.

The server (`examples/fake_listings`) serves the same listings as an HTML
page, an RSS feed and a JSON list, so every source is tested against one
live peer instead of a per-source mock.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from conftest import SAMPLE_LISTINGS, FakeListings
from watchtower import SourceError
from watchtower.sources import HttpSource, JSONAPISource, RSSSource, WebPageSource

NEW_LISTING = {"id": "3", "title": "Flat Krowodrza", "price": 2800, "description": "Fresh offer."}


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


@pytest.mark.network
def test_webpage_source_snapshots_live_server(fake_listings: FakeListings) -> None:
    """Test that the served HTML becomes Items with stable keys, links and prices."""
    items = _webpage_source(fake_listings.base_url).snapshot().items

    assert [item.key for item in items] == ["1", "2"]
    assert [item.title for item in items] == ["Flat Stare Miasto", "Studio <Kazimierz> & co"]
    assert [item.url for item in items] == [
        f"{fake_listings.base_url}/flats/1",
        f"{fake_listings.base_url}/flats/2",
    ]
    assert [item.price for item in items] == [3500.0, 2400.0]
    assert items[0].text == "Flat Stare Miasto 3 500 zł"


@pytest.mark.network
def test_webpage_source_sees_new_listing_after_change(fake_listings: FakeListings) -> None:
    """Test that editing the server's data file shows up in the next snapshot."""
    source = _webpage_source(fake_listings.base_url)
    assert [item.key for item in source.snapshot().items] == ["1", "2"]

    fake_listings.write([*SAMPLE_LISTINGS, NEW_LISTING])

    items = source.snapshot().items
    assert [item.key for item in items] == ["1", "2", "3"]
    assert items[2].title == "Flat Krowodrza"
    assert items[2].price == 2800.0


@pytest.mark.network
def test_rss_source_snapshots_live_feed(fake_listings: FakeListings) -> None:
    """Test that the served feed becomes Items keyed by guid with absolute links."""
    items = _rss_source(fake_listings.base_url).snapshot().items

    assert [item.key for item in items] == ["1", "2"]
    assert [item.title for item in items] == ["Flat Stare Miasto", "Studio <Kazimierz> & co"]
    assert [item.url for item in items] == [
        f"{fake_listings.base_url}/flats/1",
        f"{fake_listings.base_url}/flats/2",
    ]
    assert [item.price for item in items] == [3500.0, 2400.0]
    assert "Two rooms." in items[0].text
    assert items[1].published is None


@pytest.mark.network
def test_json_api_source_snapshots_live_server(fake_listings: FakeListings) -> None:
    """Test that the served JSON list becomes Items with numeric prices."""
    items = _json_api_source(fake_listings.base_url).snapshot().items

    assert [item.key for item in items] == ["1", "2"]
    assert [item.title for item in items] == ["Flat Stare Miasto", "Studio <Kazimierz> & co"]
    # The JSON endpoint has no link field, so Items come without a url.
    assert [item.url for item in items] == [None, None]
    assert [item.price for item in items] == [3500.0, 2400.0]
    assert items[0].text == "Two rooms."
    assert items[1].text == ""


@pytest.mark.network
def test_json_api_source_sees_new_listing_after_change(fake_listings: FakeListings) -> None:
    """Test that a listing added to the data file joins the next snapshot."""
    source = _json_api_source(fake_listings.base_url)
    assert [item.key for item in source.snapshot().items] == ["1", "2"]

    fake_listings.write([*SAMPLE_LISTINGS, NEW_LISTING])

    items = source.snapshot().items
    assert [item.key for item in items] == ["1", "2", "3"]
    assert items[2].price == 2800.0
    assert items[2].text == "Fresh offer."


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
