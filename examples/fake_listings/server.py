"""Fake listings website for demos and manual testing.

Serves the listings from a JSON file as an HTML page, as JSON and as an RSS
feed. The file is read again on every request, so editing it while the server
runs changes the next response, the way a real site gains new offers.

Run from the project root:

    uv run python examples/fake_listings/server.py
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from functools import partial
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TypedDict

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DATA_PATH = Path(__file__).with_name("listings.json")
DETAIL_PREFIX = "/flats/"


class Listing(TypedDict):
    """One flat offer as stored in the JSON file."""

    id: str
    title: str
    price: int
    description: str


def load_listings(path: Path) -> list[Listing]:
    """Read the listings from a JSON file.

    Args:
        path: File holding a JSON list of listings.

    Returns:
        The listings in file order.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the file is not valid JSON or a listing lacks a field.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        msg = f"{path} must contain a JSON list of listings"
        raise ValueError(msg)
    return [_to_listing(entry) for entry in data]


def _to_listing(entry: dict[str, Any]) -> Listing:
    """Check one JSON entry and convert it to a Listing."""
    try:
        return Listing(
            id=str(entry["id"]),
            title=str(entry["title"]),
            price=int(entry["price"]),
            description=str(entry.get("description", "")),
        )
    except (KeyError, TypeError) as err:
        msg = f"Invalid listing {entry!r}: {err}"
        raise ValueError(msg) from err


def format_price(price: int) -> str:
    """Format a price the way Polish sites do, e.g. 2800 -> '2 800 zł'."""
    return f"{price:,} zł".replace(",", " ")


def render_html(listings: list[Listing]) -> str:
    """Render the listings page.

    Each offer follows the HTML contract agreed with WebPageSource: a
    `div.offer` with a stable `data-id`, an `a.title` and a `span.price`.
    """
    offers = "\n".join(
        f'  <div class="offer" data-id="{escape(listing["id"])}">\n'
        f'    <a class="title" href="{DETAIL_PREFIX}{escape(listing["id"])}">'
        f"{escape(listing['title'])}</a>\n"
        f'    <span class="price">{format_price(listing["price"])}</span>\n'
        f"  </div>"
        for listing in listings
    )
    return _html_page("Flats for rent", f"<h1>Flats for rent</h1>\n{offers}")


def render_detail(listing: Listing) -> str:
    """Render the page of a single offer, the target of its title link."""
    body = (
        f"<h1>{escape(listing['title'])}</h1>\n"
        f"<p>{format_price(listing['price'])}</p>\n"
        f"<p>{escape(listing['description'])}</p>"
    )
    return _html_page(listing["title"], body)


def _html_page(title: str, body: str) -> str:
    """Wrap a body in a minimal HTML document."""
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en">\n<head><meta charset="utf-8"><title>{escape(title)}</title></head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def render_json(listings: list[Listing]) -> str:
    """Render the listings as a JSON list."""
    return json.dumps(listings, ensure_ascii=False, indent=2)


def render_rss(listings: list[Listing], base_url: str) -> str:
    """Render the listings as an RSS 2.0 feed.

    Args:
        listings: Listings to include, one feed entry each.
        base_url: Address of the server, used to build absolute links.
    """
    entries = "\n".join(
        "    <item>\n"
        f'      <guid isPermaLink="false">{escape(listing["id"])}</guid>\n'
        f"      <title>{escape(listing['title'])}</title>\n"
        f"      <link>{escape(base_url)}{DETAIL_PREFIX}{escape(listing['id'])}</link>\n"
        f"      <description>{escape(format_price(listing['price']))}. "
        f"{escape(listing['description'])}</description>\n"
        "    </item>"
        for listing in listings
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        "    <title>Flats for rent</title>\n"
        f"    <link>{escape(base_url)}/listings</link>\n"
        "    <description>Fake listings for Watchtower demos</description>\n"
        f"{entries}\n"
        "  </channel>\n"
        "</rss>\n"
    )


class ListingsHandler(BaseHTTPRequestHandler):
    """Answers GET requests from the current contents of the data file."""

    def __init__(self, *args: Any, data_path: Path, **kwargs: Any) -> None:
        """Remember the data file, then let the base class handle the request.

        The base constructor handles the request immediately, so `data_path`
        must be set before calling it.
        """
        self.data_path = data_path
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        """Route a GET request to the matching renderer."""
        try:
            listings = load_listings(self.data_path)
        except (OSError, ValueError) as err:
            self._reply(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain", f"Bad data file: {err}\n")
            return

        routes: dict[str, tuple[str, Callable[[], str]]] = {
            "/listings": ("text/html", lambda: render_html(listings)),
            "/listings.json": ("application/json", lambda: render_json(listings)),
            "/feed.xml": ("application/rss+xml", lambda: render_rss(listings, self._base_url())),
        }
        if self.path in routes:
            content_type, render = routes[self.path]
            self._reply(HTTPStatus.OK, content_type, render())
            return

        listing = self._find_detail(listings)
        if listing is not None:
            self._reply(HTTPStatus.OK, "text/html", render_detail(listing))
            return

        self._reply(HTTPStatus.NOT_FOUND, "text/plain", f"Not found: {self.path}\n")

    def _find_detail(self, listings: list[Listing]) -> Listing | None:
        """Return the listing addressed by a /flats/<id> path, if any."""
        if not self.path.startswith(DETAIL_PREFIX):
            return None
        listing_id = self.path.removeprefix(DETAIL_PREFIX)
        return next((listing for listing in listings if listing["id"] == listing_id), None)

    def _base_url(self) -> str:
        """Return the server address as the client wrote it in the Host header.

        HTTP/1.1 clients always send Host, so the fallback is only for odd clients.
        """
        return f"http://{self.headers.get('Host', 'localhost')}"

    def _reply(self, status: HTTPStatus, content_type: str, body: str) -> None:
        """Send a complete UTF-8 response."""
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(host: str, port: int, data_path: Path) -> ThreadingHTTPServer:
    """Create a server for the given data file; port 0 picks a free port."""
    handler = partial(ListingsHandler, data_path=data_path)
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and serve until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Serve fake flat listings.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH, help="listings JSON file")
    args = parser.parse_args(argv)

    with make_server(args.host, args.port, args.data) as server:
        print(f"Serving {args.data} on http://{args.host}:{args.port}/listings (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
