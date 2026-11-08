"""Shared pytest fixtures."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fake_listings.server import make_server

SAMPLE_LISTINGS: list[dict[str, Any]] = [
    {"id": "1", "title": "Flat Stare Miasto", "price": 3500, "description": "Two rooms."},
    {"id": "2", "title": "Studio <Kazimierz> & co", "price": 2400, "description": ""},
]


@dataclass
class FakeListings:
    """A running fake listings server and the data file it reads."""

    base_url: str
    data_path: Path

    def write(self, listings: list[dict[str, Any]]) -> None:
        """Replace the listings the server returns from the next request on."""
        self.data_path.write_text(json.dumps(listings), encoding="utf-8")


@pytest.fixture
def fake_listings(tmp_path: Path) -> Iterator[FakeListings]:
    """Run the fake listings server on a free local port, serving SAMPLE_LISTINGS."""
    listings = FakeListings(base_url="", data_path=tmp_path / "listings.json")
    listings.write(SAMPLE_LISTINGS)
    httpd = make_server("127.0.0.1", 0, listings.data_path)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    listings.base_url = f"http://127.0.0.1:{httpd.server_port}"
    yield listings
    httpd.shutdown()
    httpd.server_close()
