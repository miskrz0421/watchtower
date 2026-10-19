"""Tests for domain models and errors."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from watchtower.errors import NotifyError, ParseError, SourceError, WatchtowerError
from watchtower.models import Change, ChangeEvent, ChangeKind, Item, Snapshot


def test_item_equality_and_hashing() -> None:
    """Test that items with identical fields are equal and produce the same hash."""
    now = datetime.now(UTC)
    item1 = Item(key="1", title="Flat", price=2500.0, published=now)
    item2 = Item(key="1", title="Flat", price=2500.0, published=now)
    item3 = Item(key="2", title="Flat", price=2500.0, published=now)

    assert item1 == item2
    assert hash(item1) == hash(item2)
    assert item1 != item3
    assert len({item1, item2, item3}) == 2


def test_item_serialization_roundtrip() -> None:
    """Test serializing Item to dict and recreating it."""
    now = datetime.now(UTC)
    item = Item(
        key="ad-123",
        title="Apartment in city center",
        url="https://example.com/ad-123",
        price=3200.0,
        text="Description text",
        published=now,
    )
    serialized = item.to_dict()
    reconstructed = Item.from_dict(serialized)

    assert reconstructed == item
    assert repr(item) == "Item(key='ad-123', title='Apartment in city center', price=3200.0)"


def test_snapshot_serialization_roundtrip() -> None:
    """Test serializing Snapshot to dict and recreating it."""
    now = datetime.now(UTC)
    item = Item(key="k1", title="Item 1", price=100.0)
    snapshot = Snapshot(items=(item,), raw_text="raw source text", taken_at=now)

    serialized = snapshot.to_dict()
    reconstructed = Snapshot.from_dict(serialized)

    assert reconstructed.items == snapshot.items
    assert reconstructed.raw_text == snapshot.raw_text
    assert reconstructed.taken_at == snapshot.taken_at


def test_change_and_change_event_representations() -> None:
    """Test Change and ChangeEvent creation and representation."""
    item = Item(key="k1", title="Title")
    change_new = Change(kind=ChangeKind.NEW, item=item)
    change_text = Change(kind=ChangeKind.TEXT, diff_text="--- old\n+++ new\n+ added")

    assert "kind=new" in repr(change_new)
    assert "kind=text" in repr(change_text)

    event = ChangeEvent(
        watcher_name="test_watcher",
        timestamp=datetime.now(UTC),
        changes=(change_new,),
        summary="1 new item",
    )
    assert event.watcher_name == "test_watcher"
    assert len(event.changes) == 1
    assert event.summary == "1 new item"


def test_error_hierarchy() -> None:
    """Verify that specialized errors inherit from WatchtowerError."""
    assert issubclass(SourceError, WatchtowerError)
    assert issubclass(ParseError, WatchtowerError)
    assert issubclass(NotifyError, WatchtowerError)

    with pytest.raises(WatchtowerError):
        raise SourceError("Failed to fetch")

