"""Built-in data sources for Watchtower."""

from watchtower.sources.base import Source
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource
from watchtower.sources.http import HttpSource
from watchtower.sources.rss import RSSSource
from watchtower.sources.webpage import WebPageSource

__all__ = ["FakeSource", "FileSource", "HttpSource", "RSSSource", "Source", "WebPageSource"]
