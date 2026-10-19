"""Base class for data sources implementing the Template Method pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import UTC, datetime

from watchtower.errors import ParseError, SourceError
from watchtower.models import Item, Snapshot


class Source(ABC):
    """Abstract base class for all monitored data sources.

    Implements the Template Method pattern: `snapshot()` defines the invariant
    algorithm skeleton, calling abstract `fetch()` to retrieve raw data and
    `parse()` to extract structured items.
    """

    def snapshot(self) -> Snapshot:
        """Template Method: retrieve raw data and construct a snapshot.

        Calls `fetch()` followed by `parse()`. Wraps raw text and parsed items
        into a frozen `Snapshot` instance.

        Returns:
            A new Snapshot representing current source state.

        Raises:
            SourceError: If the source fails to fetch raw data.
            ParseError: If parsing the fetched data fails.
        """
        taken_at = datetime.now(UTC)
        try:
            raw_text = self.fetch()
        except SourceError:
            raise
        except Exception as err:
            msg = f"Failed to fetch data from source {self.__class__.__name__}: {err}"
            raise SourceError(msg) from err

        try:
            items = tuple(self.parse(raw_text))
        except ParseError:
            raise
        except Exception as err:
            msg = f"Failed to parse content from source {self.__class__.__name__}: {err}"
            raise ParseError(msg) from err

        return Snapshot(
            items=items,
            raw_text=raw_text,
            taken_at=taken_at,
        )

    @abstractmethod
    def fetch(self) -> str:
        """Fetch raw textual content from the external medium.

        Returns:
            Raw string content (HTML, XML, JSON, plaintext, etc.).

        Raises:
            SourceError: On network, file, or protocol errors.
        """

    @abstractmethod
    def parse(self, raw: str) -> Iterable[Item]:
        """Parse raw content into an iterable of Item instances.

        Args:
            raw: Raw string content returned by `fetch()`.

        Returns:
            An iterable (e.g. generator or list) of parsed Items.

        Raises:
            ParseError: When content format is invalid.
        """
