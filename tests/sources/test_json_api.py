"""Tests for JSONAPISource."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from conftest import SAMPLE_LISTINGS, FakeListings
from watchtower import ParseError, SourceError, create_source
from watchtower.sources import JSONAPISource

FIXTURES = Path(__file__).parents[1] / "fixtures"
NEW_LISTING = {"id": "3", "title": "Flat Krowodrza", "price": 2800, "description": "Fresh offer."}


def _saved_listings() -> str:
    """Return the saved JSON listings fixture as text."""
    return (FIXTURES / "listings.json").read_text(encoding="utf-8")


def _json_listings_source() -> JSONAPISource:
    """Build a JSONAPISource reading the saved listings fixture."""
    return JSONAPISource(
        url="http://example.test/api/listings",
        items_path="data.offers",
        key_field="id",
        title_field="title",
        url_field="link",
        price_field="price",
        text_field="description",
    )


def _json_api_source(base_url: str) -> JSONAPISource:
    """Build a JSONAPISource reading the server's JSON endpoint."""
    return JSONAPISource(
        url=f"{base_url}/listings.json", price_field="price", text_field="description"
    )


def test_json_api_source_parses_saved_listings() -> None:
    """Test keys, titles, links, prices and descriptions from a saved response."""
    items = list(_json_listings_source().parse(_saved_listings()))

    assert [item.key for item in items] == ["1", "2", "3"]
    assert [item.title for item in items] == [
        "Flat Krowodrza",
        "Studio Kazimierz",
        "Flat without price",
    ]
    assert [item.url for item in items] == [
        "http://example.test/flats/1",
        "http://example.test/flats/2",
        "http://other.test/flats/3",
    ]
    # A numeric field is a price as it is; a string goes through price parsing;
    # null means no price.
    assert [item.price for item in items] == [2800.0, 2400.5, None]
    assert items[0].text == "2 rooms, 45 m2, 2 800 zł"
    assert items[1].text == "1 room, 30 m2"


@pytest.mark.parametrize("items_path", [None, "", "  "])
def test_json_api_source_reads_list_at_response_root(items_path: str | None) -> None:
    """Test that without an items_path (or a blank one) the response itself is the list."""
    raw = json.dumps([{"id": "a", "title": "One"}, {"id": "b", "title": "Two"}])
    source = JSONAPISource(url="http://example.test/api/listings", items_path=items_path)

    items = list(source.parse(raw))

    assert [item.key for item in items] == ["a", "b"]
    assert [item.title for item in items] == ["One", "Two"]


def test_json_api_source_uses_custom_field_names() -> None:
    """Test that field names point at the values an API actually provides."""
    raw = json.dumps(
        [
            {
                "sku": "x-1",
                "name": "Widget",
                "href": "http://example.test/x/1",
                "amount": "9,99 €",
                "note": "Cheap",
            }
        ]
    )
    source = JSONAPISource(
        url="http://example.test/api/items",
        key_field="sku",
        title_field="name",
        url_field="href",
        price_field="amount",
        text_field="note",
    )

    items = list(source.parse(raw))

    assert len(items) == 1
    assert items[0].key == "x-1"
    assert items[0].title == "Widget"
    assert items[0].url == "http://example.test/x/1"
    assert items[0].price == 9.99
    assert items[0].text == "Cheap"


def test_json_api_source_ignores_fields_it_was_not_given() -> None:
    """Test that extra object fields and absent optional fields give default values."""
    raw = json.dumps([{"id": "1", "title": "Flat", "note": "unexpected"}])

    items = list(JSONAPISource(url="http://example.test/api/listings").parse(raw))

    assert len(items) == 1
    assert items[0].url is None
    assert items[0].price is None
    assert items[0].text == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2800, 2800.0),
        (2800.5, 2800.5),
        ("2 800 zł", 2800.0),
        ("9,99 €", 9.99),
        (None, None),
        (True, None),
        ("", None),
        ("Price on request", None),
    ],
)
def test_json_api_source_price_field_forms(value: object, expected: float | None) -> None:
    """Test that numbers pass through, text is parsed, and junk means no price."""
    raw = json.dumps([{"id": "1", "title": "Flat", "price": value}])
    source = JSONAPISource(url="http://example.test/api/listings", price_field="price")

    items = list(source.parse(raw))

    assert items[0].price == expected


def test_json_api_source_accepts_empty_list() -> None:
    """Test that a valid response with no objects gives no Items."""
    assert list(JSONAPISource(url="http://example.test/api/listings").parse("[]")) == []


def test_json_api_source_rejects_text_that_is_not_json() -> None:
    """Test that an error page or truncated body is a parse error."""
    source = JSONAPISource(url="http://example.test/api/listings")

    with pytest.raises(ParseError, match="not valid JSON"):
        source.parse("<html><body>502 Bad Gateway</body></html>")


def test_json_api_source_rejects_missing_path() -> None:
    """Test that a path absent from the response is a parse error."""
    source = JSONAPISource(url="http://example.test/api/listings", items_path="data.offers")

    with pytest.raises(ParseError, match="Path 'data.offers' does not exist"):
        source.parse('{"data": {}}')


def test_json_api_source_rejects_path_to_non_list() -> None:
    """Test that a path leading to an object instead of a list is a parse error."""
    source = JSONAPISource(url="http://example.test/api/listings", items_path="data.offers")

    with pytest.raises(ParseError, match="Path 'data.offers' does not lead to a list"):
        source.parse('{"data": {"offers": {"id": "1", "title": "Flat"}}}')


def test_json_api_source_rejects_response_that_is_not_a_list() -> None:
    """Test that a JSON object without an items_path is a parse error."""
    source = JSONAPISource(url="http://example.test/api/listings")

    with pytest.raises(ParseError, match="Response is not a JSON list"):
        source.parse('{"offers": []}')


def test_json_api_source_rejects_non_object_entry() -> None:
    """Test that a bare value in the list is reported with its position."""
    source = JSONAPISource(url="http://example.test/api/listings")

    with pytest.raises(ParseError, match="Object 1 in the list is not a JSON object"):
        source.parse('["just a string"]')


def test_json_api_source_rejects_object_without_key() -> None:
    """Test that an object without a stable key is a parse error."""
    source = JSONAPISource(url="http://example.test/api/listings")

    with pytest.raises(ParseError, match="Object 1 has no 'id'"):
        source.parse('[{"title": "Flat"}]')


def test_json_api_source_rejects_object_without_title() -> None:
    """Test that an object without a title is a parse error naming its key."""
    source = JSONAPISource(url="http://example.test/api/listings")

    with pytest.raises(ParseError, match=r"Object 1 \('1'\) has no 'title'"):
        source.parse('[{"id": "1"}]')


def test_json_api_source_rejects_blank_title() -> None:
    """Test that a whitespace-only title counts as missing."""
    source = JSONAPISource(url="http://example.test/api/listings")

    with pytest.raises(ParseError, match="has no 'title'"):
        source.parse('[{"id": "1", "title": "   "}]')


def test_registry_creates_json_api_source() -> None:
    """Test instantiating JSONAPISource via registry factory."""
    source = create_source(
        "json_api", url="http://example.test/api/listings", items_path="data.offers"
    )

    assert isinstance(source, JSONAPISource)


def test_json_api_snapshot_parses_downloaded_json() -> None:
    """Test the fetch and parse steps together using an offline transport."""
    raw = _saved_listings()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=raw))
    source = JSONAPISource(
        url="http://example.test/api/listings",
        items_path="data.offers",
        key_field="id",
        title_field="title",
        url_field="link",
        price_field="price",
        text_field="description",
        transport=transport,
    )

    snapshot = source.snapshot()

    assert snapshot.raw_text == raw
    assert [item.key for item in snapshot.items] == ["1", "2", "3"]
    assert [item.price for item in snapshot.items] == [2800.0, 2400.5, None]


def test_json_api_snapshot_propagates_parse_error() -> None:
    """Test that validation errors survive the Source.snapshot() template method."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text='{"data": {"offers": [{"id": "1"}]}}')
    )
    source = JSONAPISource(
        url="http://example.test/api/listings",
        items_path="data.offers",
        transport=transport,
    )

    with pytest.raises(ParseError, match="has no 'title'"):
        source.snapshot()


def test_json_api_snapshot_reports_error_status_as_source_error() -> None:
    """Test that an HTTP error from the API is reported as SourceError."""
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    source = JSONAPISource(
        url="http://example.test/api/listings",
        items_path="data.offers",
        transport=transport,
    )

    with pytest.raises(SourceError):
        source.snapshot()


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
