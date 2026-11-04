"""FileSource for reading content from local files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from watchtower.errors import SourceError
from watchtower.models import Item
from watchtower.registry import register_source
from watchtower.sources.base import Source


@register_source("file")
class FileSource(Source):
    """Source that reads the contents of a local file on disk."""

    def __init__(self, path: str | Path, encoding: str = "utf-8") -> None:
        """Initialize FileSource with a file path and character encoding.

        Args:
            path: Path to the local file to monitor.
            encoding: Text encoding of the file (defaults to 'utf-8').
        """
        self.path = Path(path)
        self.encoding = encoding

    def fetch(self) -> str:
        """Read and return the text content of the target file.

        Returns:
            String content of the file.

        Raises:
            SourceError: If the file is missing or cannot be opened.
        """
        if not self.path.exists():
            msg = f"Target file does not exist: {self.path}"
            raise SourceError(msg)

        try:
            return self.path.read_text(encoding=self.encoding)
        except Exception as err:
            msg = f"Failed to read file {self.path}: {err}"
            raise SourceError(msg) from err

    def parse(self, raw: str) -> Iterable[Item]:
        """Parse raw file content.

        In the base file source, content is treated as unstructured raw text,
        so this yields no structured items by default.

        Args:
            raw: Raw text content from the file.

        Returns:
            Empty iterable of items.
        """
        return ()
