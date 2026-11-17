"""Tests for FileSource."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchtower import SourceError, create_source
from watchtower.sources import FileSource


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


def test_registry_creates_file_source(tmp_path: Path) -> None:
    """Test instantiating FileSource via registry factory."""
    f = tmp_path / "reg.txt"
    f.write_text("content", encoding="utf-8")
    file_src = create_source("file", path=f)
    assert isinstance(file_src, FileSource)
