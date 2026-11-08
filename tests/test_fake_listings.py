"""Tests for the fake listings server in examples/fake_listings."""

from __future__ import annotations

import feedparser
import httpx
import pytest
from bs4 import BeautifulSoup
from fake_listings.server import (
    Listing,
    format_price,
    load_listings,
    render_html,
    render_rss,
)

from conftest import SAMPLE_LISTINGS, FakeListings

LISTINGS = [Listing(**entry) for entry in SAMPLE_LISTINGS]


@pytest.mark.parametrize(
    ("price", "expected"),
    [(800, "800 zł"), (2800, "2 800 zł"), (1250000, "1 250 000 zł")],
)
def test_format_price_groups_thousands(price: int, expected: str) -> None:
    """Test that prices are written with spaces between thousands."""
    assert format_price(price) == expected


def test_render_html_follows_webpage_contract() -> None:
    """Test that every offer has the elements WebPageSource relies on."""
    soup = BeautifulSoup(render_html(LISTINGS), "html.parser")
    offers = soup.select(".offer")

    assert [offer["data-id"] for offer in offers] == ["1", "2"]
    assert offers[0].select_one(".title").get_text() == "Flat Stare Miasto"
    assert offers[0].select_one(".title")["href"] == "/flats/1"
    assert offers[0].select_one(".price").get_text() == "3 500 zł"


def test_render_html_escapes_titles() -> None:
    """Test that HTML special characters in a title cannot break the page."""
    html = render_html(LISTINGS)

    assert "Studio &lt;Kazimierz&gt; &amp; co" in html
    assert "<Kazimierz>" not in html


def test_render_rss_has_one_entry_per_listing() -> None:
    """Test that the feed parses and each entry keeps the listing id and an absolute link."""
    feed = feedparser.parse(render_rss(LISTINGS, "http://test:8000"))

    assert not feed.bozo
    assert [entry.id for entry in feed.entries] == ["1", "2"]
    assert feed.entries[0].link == "http://test:8000/flats/1"
    assert feed.entries[1].title == "Studio <Kazimierz> & co"


def test_load_listings_rejects_missing_field(fake_listings: FakeListings) -> None:
    """Test that a listing without a price is reported as invalid data."""
    fake_listings.write([{"id": "1", "title": "No price"}])

    with pytest.raises(ValueError, match="Invalid listing"):
        load_listings(fake_listings.data_path)


@pytest.mark.network
def test_server_routes(fake_listings: FakeListings) -> None:
    """Test the content of each route."""
    base_url = fake_listings.base_url
    html = httpx.get(f"{base_url}/listings")
    assert html.status_code == 200
    assert html.headers["Content-Type"] == "text/html; charset=utf-8"
    assert 'data-id="1"' in html.text

    assert httpx.get(f"{base_url}/listings.json").json()[0]["title"] == "Flat Stare Miasto"
    assert "<rss" in httpx.get(f"{base_url}/feed.xml").text
    assert "Two rooms." in httpx.get(f"{base_url}/flats/1").text
    assert httpx.get(f"{base_url}/flats/99").status_code == 404
    assert httpx.get(f"{base_url}/nothing").status_code == 404


@pytest.mark.network
def test_server_reads_data_file_on_every_request(fake_listings: FakeListings) -> None:
    """Test that editing the data file shows up on the next request."""
    url = f"{fake_listings.base_url}/listings"
    assert "Flat Krowodrza" not in httpx.get(url).text

    new = {"id": "3", "title": "Flat Krowodrza", "price": 2800, "description": ""}
    fake_listings.write([*SAMPLE_LISTINGS, new])

    assert "Flat Krowodrza" in httpx.get(url).text


@pytest.mark.network
def test_server_reports_broken_data_file(fake_listings: FakeListings) -> None:
    """Test that invalid JSON gives a 500 error instead of crashing the server."""
    fake_listings.data_path.write_text("[{broken", encoding="utf-8")

    response = httpx.get(f"{fake_listings.base_url}/listings")

    assert response.status_code == 500
    assert "Bad data file" in response.text
