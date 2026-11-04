"""Built-in data sources for Watchtower."""

from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource

__all__ = ["FakeSource", "FileSource", "Source"]
