"""Domain models representing items, snapshots, and detected changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class Item:
    """Represents a single monitored entity (e.g., an ad listing or feed post).

    Items are frozen and hashable by value, allowing them to be compared
    and processed efficiently using Python sets.
    """

    key: str
    title: str
    url: str | None = None
    price: float | None = None
    text: str = ""
    published: datetime | None = None

    def __repr__(self) -> str:
        """Return a compact, readable representation of the item."""
        price_str = f", price={self.price}" if self.price is not None else ""
        return f"Item(key={self.key!r}, title={self.title!r}{price_str})"

    def to_dict(self) -> dict[str, Any]:
        """Convert item to a dictionary suitable for JSON serialization."""
        return {
            "key": self.key,
            "title": self.title,
            "url": self.url,
            "price": self.price,
            "text": self.text,
            "published": self.published.isoformat() if self.published else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Item:
        """Create an Item instance from a dictionary.

        Args:
            data: Dictionary containing item attributes.

        Returns:
            A reconstructed Item instance.
        """
        published = None
        if data.get("published"):
            published = datetime.fromisoformat(data["published"])
        return cls(
            key=str(data["key"]),
            title=str(data["title"]),
            url=data.get("url"),
            price=float(data["price"]) if data.get("price") is not None else None,
            text=str(data.get("text", "")),
            published=published,
        )


@dataclass(frozen=True)
class Snapshot:
    """State of a monitored source captured at a specific point in time.

    Contains structured items as well as raw source text.
    """

    items: tuple[Item, ...] = ()
    raw_text: str = ""
    taken_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to a dictionary for serialization."""
        return {
            "items": [item.to_dict() for item in self.items],
            "raw_text": self.raw_text,
            "taken_at": self.taken_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        """Recreate a Snapshot from serialized dictionary data.

        Args:
            data: Serialized snapshot dictionary.

        Returns:
            A reconstructed Snapshot instance.
        """
        items = tuple(Item.from_dict(item_dict) for item_dict in data.get("items", []))
        taken_at = (
            datetime.fromisoformat(data["taken_at"]) if "taken_at" in data else datetime.now(UTC)
        )
        return cls(
            items=items,
            raw_text=str(data.get("raw_text", "")),
            taken_at=taken_at,
        )


class ChangeKind(StrEnum):
    """Enumeration of possible change types."""

    NEW = "new"
    REMOVED = "removed"
    CHANGED = "changed"
    TEXT = "text"


@dataclass(frozen=True)
class Change:
    """A single difference identified between two snapshots."""

    kind: ChangeKind
    item: Item | None = None
    before: Item | None = None
    diff_text: str | None = None

    def __repr__(self) -> str:
        """Return a concise representation of the change."""
        if self.kind == ChangeKind.TEXT:
            preview = (self.diff_text or "")[:30].replace("\n", " ")
            return f"Change(kind={self.kind.value}, diff_text={preview!r}...)"
        if self.item is not None:
            return f"Change(kind={self.kind.value}, item={self.item!r})"
        return f"Change(kind={self.kind.value})"


@dataclass(frozen=True)
class ChangeEvent:
    """Event delivered to notifiers containing filtered changes."""

    watcher_name: str
    timestamp: datetime
    changes: tuple[Change, ...]
    summary: str
