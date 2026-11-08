"""Tests for base Source, FakeSource, and FileSource."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from watchtower.errors import ParseError, SourceError
from watchtower.models import Item, Snapshot
from watchtower.registry import create_source
from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource
from watchtower.sources.parsing import parse_price
from watchtower.sources.rss import RSSSource
from watchtower.sources.webpage import WebPageSource

FIXTURES = Path(__file__).parent / "fixtures"


class DummyWorkingSource(Source):
    """Concrete source for testing template method execution."""

    def fetch(self) -> str:
        return "id1:Title1\nid2:Title2"

    def parse(self, raw: str) -> Iterable[Item]:
        for line in raw.strip().splitlines():
            key, title = line.split(":")
            yield Item(key=key, title=title)


class FailingFetchSource(Source):
    """Source that fails during fetch."""

    def fetch(self) -> str:
        msg = "Network down"
        raise OSError(msg)

    def parse(self, raw: str) -> Iterable[Item]:
        return ()


class FailingParseSource(Source):
    """Source that fails during parse."""

    def fetch(self) -> str:
        return "invalid content"

    def parse(self, raw: str) -> Iterable[Item]:
        msg = "Corrupted data"
        raise ValueError(msg)


def test_source_template_method() -> None:
    """Test that snapshot() calls fetch() and parse() and returns populated Snapshot."""
    source = DummyWorkingSource()
    snap = source.snapshot()

    assert isinstance(snap, Snapshot)
    assert snap.raw_text == "id1:Title1\nid2:Title2"
    assert len(snap.items) == 2
    assert snap.items[0].key == "id1"
    assert snap.items[0].title == "Title1"
    assert snap.items[1].key == "id2"


def test_source_template_method_exception_wrapping() -> None:
    """Test that unexpected exceptions during fetch or parse are wrapped.

    Ensures they are wrapped in SourceError / ParseError.
    """
    with pytest.raises(SourceError, match="Failed to fetch data"):
        FailingFetchSource().snapshot()

    with pytest.raises(ParseError, match="Failed to parse content"):
        FailingParseSource().snapshot()


def test_fake_source_cycling() -> None:
    """Test FakeSource sequential snapshot retrieval and repeating the last entry."""
    source = FakeSource(contents=["version 1", "version 2"])

    snap1 = source.snapshot()
    assert snap1.raw_text == "version 1"

    snap2 = source.snapshot()
    assert snap2.raw_text == "version 2"

    snap3 = source.snapshot()
    assert snap3.raw_text == "version 2"


def test_fake_source_replays_scripted_items_in_order() -> None:
    """Test that scripted snapshots replay their items, repeating the last one."""
    first = Snapshot(items=(Item(key="1", title="One"),), raw_text="one")
    second = Snapshot(items=(Item(key="2", title="Two"),), raw_text="two")
    source = FakeSource(snapshots=[first, second])

    assert source.snapshot().items == first.items
    assert source.snapshot().items == second.items
    assert source.snapshot().items == second.items


def test_file_source_read_and_error(tmp_path: Path) -> None:
    """Test FileSource reads existing file and raises SourceError on missing file."""
    test_file = tmp_path / "sample.txt"
    test_file.write_text("Hello Watchtower", encoding="utf-8")

    source = FileSource(path=test_file)
    snap = source.snapshot()
    assert snap.raw_text == "Hello Watchtower"
    assert snap.items == ()

    missing_source = FileSource(path=tmp_path / "nonexistent.txt")
    with pytest.raises(SourceError, match="Target file does not exist"):
        missing_source.snapshot()


def test_registry_creates_fake_and_file_sources(tmp_path: Path) -> None:
    """Test instantiating FakeSource and FileSource via registry factory."""
    fake = create_source("fake", contents=["step 1"])
    assert isinstance(fake, FakeSource)

    f = tmp_path / "reg.txt"
    f.write_text("content", encoding="utf-8")
    file_src = create_source("file", path=f)
    assert isinstance(file_src, FileSource)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 999 zł", 2999.0),
        ("2\u00a0999 zł", 2999.0),
        ("2\u202f999 zł", 2999.0),
        ("800 zł", 800.0),
        ("1 250 000 zł", 1250000.0),
        ("1.250.000 zł", 1250000.0),
        ("2 999,99 zł", 2999.99),
        ("2,999.99 zł", 2999.99),
        ("2999.50 zł", 2999.5),
        ("2 999 zł/mies.", 2999.0),
        ("Flat 2, 2 800 zł", 2800.0),
        ("50 m², 2 800 zł", 2800.0),
        ("3 pokoje 2800 zł", 2800.0),
        ("2 rooms, 45 m2, 3 100 PLN", 3100.0),
        ("Price: € 1 200", 1200.0),
        ("5 zleceń, 2 000 zł", 2000.0),
        ("Flat 2, 2 800", 2.0),  # no currency: the first number wins
        ("No price", None),
        ("Price on request", None),
        ("", None),
    ],
)
def test_parse_price(text: str, expected: float | None) -> None:
    """Test price parsing with different separators and missing prices."""
    assert parse_price(text) == expected


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
