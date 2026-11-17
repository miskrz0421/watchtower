"""Tests for FakeSource."""

from __future__ import annotations

from watchtower import Item, Snapshot, create_source
from watchtower.sources import FakeSource


def test_fake_source_cycling() -> None:
    """Test FakeSource sequential snapshot retrieval and repeating the last entry."""
    source = FakeSource(contents=["version 1", "version 2"])

    snap1 = source.snapshot()
    assert snap1.raw_text == "version 1"

    snap2 = source.snapshot()
    assert snap2.raw_text == "version 2"

    snap3 = source.snapshot()
    assert snap3.raw_text == "version 2"


def test_fake_source_replays_scripted_items_in_order() -> None:
    """Test that scripted snapshots replay their items, repeating the last one."""
    first = Snapshot(items=(Item(key="1", title="One"),), raw_text="one")
    second = Snapshot(items=(Item(key="2", title="Two"),), raw_text="two")
    source = FakeSource(snapshots=[first, second])

    assert source.snapshot().items == first.items
    assert source.snapshot().items == second.items
    assert source.snapshot().items == second.items


def test_registry_creates_fake_source() -> None:
    """Test instantiating FakeSource via registry factory."""
    fake = create_source("fake", contents=["step 1"])
    assert isinstance(fake, FakeSource)
