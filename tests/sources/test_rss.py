"""Tests for RSSSource."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from conftest import FakeListings
from watchtower import ParseError
from watchtower.sources import RSSSource
from watchtower.sources._rss import _published

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _feed(*entries: str) -> str:
    """Build a minimal RSS document around the given item elements."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss version="2.0"><channel><title>Test feed</title>'
        f"{''.join(entries)}</channel></rss>"
    )


def _saved_feed() -> str:
    """Return the saved RSS fixture as text."""
    return (FIXTURES / "feed.xml").read_text(encoding="utf-8")


def _rss_source(base_url: str) -> RSSSource:
    """Build an RSSSource reading the server's feed."""
    return RSSSource(url=f"{base_url}/feed.xml")


def test_rss_source_parses_saved_feed() -> None:
    """Test that an RSS fixture becomes Items, with the link as key when there is no guid."""
    items = list(RSSSource(url="http://example.test/feed.xml").parse(_saved_feed()))

    assert [item.key for item in items] == [
        "entry-1",
        "http://example.test/flats/2",
        "entry-3",
        "entry-4",
    ]
    assert [item.title for item in items] == [
        "Flat Krowodrza",
        "Flat Kazimierz",
        "Flat Podgórze",
        "Flat without date",
    ]
    assert [item.url for item in items] == [
        "http://example.test/flats/1",
        "http://example.test/flats/2",
        "http://example.test/flats/3",
        "http://example.test/flats/4",
    ]
    assert [item.price for item in items] == [2800.0, None, 3200.0, 1900.0]
    assert "2 800 zł" in items[0].text
    assert items[1].text == "No price yet."


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, datetime(2023, 11, 6, 10, 0, tzinfo=UTC)),
        (1, datetime(2023, 11, 7, 13, 30, tzinfo=UTC)),
        (2, datetime(2023, 11, 7, 18, 45, tzinfo=UTC)),
        (3, None),
    ],
)
def test_rss_source_normalizes_publication_dates_to_utc(
    index: int, expected: datetime | None
) -> None:
    """Test that dates with different time zones become UTC and a missing date stays None."""
    items = list(RSSSource(url="http://example.test/feed.xml").parse(_saved_feed()))

    assert items[index].published == expected


def test_rss_source_accepts_id_without_link_or_date() -> None:
    """Test that the id is used as key and that optional fields may be absent."""
    raw = _feed('<item><guid isPermaLink="false">entry-1</guid><title>Flat</title></item>')

    items = list(RSSSource(url="http://example.test/feed.xml").parse(raw))

    assert len(items) == 1
    assert items[0].key == "entry-1"
    assert items[0].url is None
    assert items[0].published is None


@pytest.mark.parametrize(
    ("description", "price_element", "expected"),
    [
        ("2 800 zł", "9 999 zł", 2800.0),
        ("No price here", "2 500 zł", 2500.0),
        ("No price here", None, None),
    ],
)
def test_rss_source_price_comes_from_description_or_price_element(
    description: str, price_element: str | None, expected: float | None
) -> None:
    """Test that the description wins and the price element is the fallback."""
    price_xml = f"<price>{price_element}</price>" if price_element is not None else ""
    raw = _feed(
        '<item><guid isPermaLink="false">entry-1</guid><title>Flat</title>'
        f"<description>{description}</description>{price_xml}</item>"
    )

    items = list(RSSSource(url="http://example.test/feed.xml").parse(raw))

    assert items[0].price == expected


def test_rss_source_parses_atom_feed() -> None:
    """Test that Atom entries use their id, link href and updated timestamp."""
    raw = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>Test feed</title><id>urn:feed</id>'
        "<updated>2023-11-08T09:00:00+01:00</updated>"
        "<entry><id>urn:entry:1</id><title>Flat Atom</title>"
        '<link href="http://example.test/flats/1"/>'
        "<summary>2 500 zł</summary>"
        "<updated>2023-11-08T09:30:00+01:00</updated></entry></feed>"
    )

    items = list(RSSSource(url="http://example.test/feed.xml").parse(raw))

    assert len(items) == 1
    assert items[0].key == "urn:entry:1"
    assert items[0].title == "Flat Atom"
    assert items[0].url == "http://example.test/flats/1"
    assert items[0].price == 2500.0
    assert items[0].published == datetime(2023, 11, 8, 8, 30, tzinfo=UTC)


def test_rss_source_rejects_entry_without_id_or_link() -> None:
    """Test that an entry without a stable key is reported as a parse error."""
    raw = _feed("<item><title>No key</title></item>")

    with pytest.raises(ParseError, match="no id or link"):
        list(RSSSource(url="http://example.test/feed.xml").parse(raw))


def test_rss_source_rejects_entry_without_title() -> None:
    """Test that an entry without a title is reported as a parse error."""
    raw = _feed("<item><guid>entry-1</guid></item>")

    with pytest.raises(ParseError, match="has no title"):
        list(RSSSource(url="http://example.test/feed.xml").parse(raw))


def test_rss_source_rejects_entry_with_blank_title() -> None:
    """Test that a whitespace-only title counts as missing."""
    raw = _feed("<item><guid>entry-1</guid><title>   </title></item>")

    with pytest.raises(ParseError, match="has no title"):
        list(RSSSource(url="http://example.test/feed.xml").parse(raw))


@pytest.mark.parametrize(
    "raw",
    ["<html><body>502 Bad Gateway</body></html>", "not a feed", ""],
)
def test_rss_source_rejects_text_that_is_not_a_feed(raw: str) -> None:
    """Test that an error page is a parse error, not a feed whose Items were all removed."""
    with pytest.raises(ParseError, match="not an RSS or Atom feed"):
        list(RSSSource(url="http://example.test/feed.xml").parse(raw))


def test_rss_source_accepts_feed_without_entries() -> None:
    """Test that a valid feed with no entries gives no Items."""
    assert list(RSSSource(url="http://example.test/feed.xml").parse(_feed())) == []


def test_rss_snapshot_propagates_parse_error() -> None:
    """Test that validation errors survive the Source.snapshot() template method."""
    raw = _feed("<item><title>No key</title></item>")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=raw))
    source = RSSSource("http://test/feed.xml", transport=transport)

    with pytest.raises(ParseError, match="no id or link"):
        source.snapshot()


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


def test_published_rejects_invalid_parsed_type() -> None:
    """A non-sequence published_parsed raises ParseError."""
    entry = {"published_parsed": "not-a-tuple"}
    with pytest.raises(ParseError, match="invalid publication date"):
        _published(entry, 1)


def test_published_rejects_invalid_date_parts() -> None:
    """Non-integer date parts raise ParseError."""
    entry = {"published_parsed": ("not", "a", "date", 1, 2, 3)}
    with pytest.raises(ParseError, match="invalid publication date"):
        _published(entry, 1)
