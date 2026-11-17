"""Tests for WebPageSource."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from conftest import SAMPLE_LISTINGS, FakeListings
from watchtower import ParseError
from watchtower.sources import WebPageSource

FIXTURES = Path(__file__).parents[1] / "fixtures"
NEW_LISTING = {"id": "3", "title": "Flat Krowodrza", "price": 2800, "description": "Fresh offer."}


def _saved_html() -> str:
    """Return the saved HTML fixture as text."""
    return (FIXTURES / "listings.html").read_text(encoding="utf-8")


def _listings_source(
    *,
    key_attribute: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> WebPageSource:
    """Build a WebPageSource for the saved listings fixture."""
    return WebPageSource(
        url="http://example.test/listings",
        selector=".offer",
        title_selector=".title",
        price_selector=".price",
        key_attribute=key_attribute,
        transport=transport,
    )


def _webpage_source(base_url: str) -> WebPageSource:
    """Build a WebPageSource reading the server's listings page."""
    return WebPageSource(
        url=f"{base_url}/listings",
        selector=".offer",
        title_selector=".title",
        price_selector=".price",
        key_attribute="data-id",
    )


def test_webpage_source_parses_saved_html() -> None:
    """Test keys, titles, absolute links and parsed prices from a saved page."""
    items = list(_listings_source(key_attribute="data-id").parse(_saved_html()))

    assert [item.key for item in items] == ["1", "2", "3"]
    assert [item.title for item in items] == [
        "Flat Krowodrza",
        "Studio Kazimierz",
        "Flat with absolute link",
    ]
    assert [item.url for item in items] == [
        "http://example.test/flats/1",
        "http://example.test/flats/2",
        "http://other.test/flats/3",
    ]
    assert [item.price for item in items] == [2800.0, 2400.5, None]
    assert "2 800 zł" in items[0].text


def test_webpage_source_key_falls_back_to_link() -> None:
    """Test that without a key attribute the first link's href becomes the key."""
    items = list(_listings_source().parse(_saved_html()))

    assert [item.key for item in items] == [
        "/flats/1",
        "flats/2",
        "http://other.test/flats/3",
    ]


def test_webpage_source_blank_key_attribute_falls_back_to_link() -> None:
    """Test that a blank key attribute is treated as missing."""
    html = '<div class="offer" data-id="   "><a class="title" href="/flats/1">Flat</a></div>'
    source = WebPageSource(
        url="http://example.test/listings",
        selector=".offer",
        title_selector=".title",
        key_attribute="data-id",
    )

    items = list(source.parse(html))

    assert len(items) == 1
    assert items[0].key == "/flats/1"


def test_webpage_source_key_falls_back_to_title() -> None:
    """Test that an element without a key attribute or link uses its title as key."""
    html = '<div class="offer"><span class="title">Only title</span></div>'
    source = WebPageSource(
        url="http://example.test/listings",
        selector=".offer",
        title_selector=".title",
    )

    items = list(source.parse(html))

    assert len(items) == 1
    assert items[0].key == "Only title"
    assert items[0].url is None
    assert items[0].price is None


def test_webpage_source_uses_element_text_as_title() -> None:
    """Test that without a title selector the element's own text is the title."""
    html = '<div class="offer">Whole offer text</div>'
    source = WebPageSource(url="http://example.test/listings", selector=".offer")

    items = list(source.parse(html))

    assert len(items) == 1
    assert items[0].title == "Whole offer text"
    assert items[0].key == "Whole offer text"
    assert items[0].price is None


@pytest.mark.parametrize(
    ("html", "title_selector"),
    [
        ('<div class="offer"><span class="price">2 800 zł</span></div>', ".title"),
        ('<div class="offer"><span class="title">  </span></div>', ".title"),
        ('<div class="offer"></div>', None),
    ],
)
def test_webpage_source_rejects_element_without_title(
    html: str, title_selector: str | None
) -> None:
    """Test that an element without a title is a parse error instead of an Item keyed ''."""
    source = WebPageSource(
        url="http://example.test/listings",
        selector=".offer",
        title_selector=title_selector,
    )

    with pytest.raises(ParseError, match="Element 1 matching '.offer' has no title"):
        list(source.parse(html))


def test_webpage_source_with_no_matching_elements_gives_no_items() -> None:
    """Test that a page without matching elements gives an empty list (ADR-012)."""
    source = WebPageSource(url="http://example.test/listings", selector=".offer")

    assert list(source.parse("<html><body><p>No offers</p></body></html>")) == []


def test_webpage_snapshot_parses_downloaded_html() -> None:
    """Test the fetch and parse steps together using an offline transport."""
    html = _saved_html()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=html))
    source = _listings_source(key_attribute="data-id", transport=transport)

    snapshot = source.snapshot()

    assert snapshot.raw_text == html
    assert [item.key for item in snapshot.items] == ["1", "2", "3"]


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
