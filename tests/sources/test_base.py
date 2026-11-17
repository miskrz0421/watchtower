"""Tests for base Source template method and error handling."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from watchtower import Item, ParseError, Snapshot, SourceError
from watchtower.sources import Source


class DummyWorkingSource(Source):
    """Concrete source for testing template method execution."""

    def fetch(self) -> str:
        """Return two scripted lines."""
        return "id1:Title1\nid2:Title2"

    def parse(self, raw: str) -> Iterable[Item]:
        """Turn each `key:title` line into an Item."""
        for line in raw.strip().splitlines():
            key, title = line.split(":")
            yield Item(key=key, title=title)


class FailingFetchSource(Source):
    """Source that fails during fetch."""

    def fetch(self) -> str:
        """Fail the way a broken network does."""
        msg = "Network down"
        raise OSError(msg)

    def parse(self, raw: str) -> Iterable[Item]:
        """Return no items; never reached."""
        return ()


class FailingParseSource(Source):
    """Source that fails during parse."""

    def fetch(self) -> str:
        """Return text that parse() rejects."""
        return "invalid content"

    def parse(self, raw: str) -> Iterable[Item]:
        """Fail the way a broken parser does."""
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
