"""Tests for base Source, FakeSource, and FileSource."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from watchtower.errors import ParseError, SourceError
from watchtower.models import Item, Snapshot
from watchtower.registry import create
from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource


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
    fake = create("source", "fake", contents=["step 1"])
    assert isinstance(fake, FakeSource)

    f = tmp_path / "reg.txt"
    f.write_text("content", encoding="utf-8")
    file_src = create("source", "file", path=f)
    assert isinstance(file_src, FileSource)
