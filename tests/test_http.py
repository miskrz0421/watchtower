"""Tests for HttpSource, using httpx.MockTransport so no network is needed."""

from __future__ import annotations

from collections.abc import Iterable

import httpx
import pytest

from watchtower.errors import SourceError
from watchtower.models import Item
from watchtower.sources.http import USER_AGENT, HttpSource


class PlainHttpSource(HttpSource):
    """HttpSource that produces no items."""

    def parse(self, raw: str) -> Iterable[Item]:
        """Return no items."""
        return ()


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
