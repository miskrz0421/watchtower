"""Tests for Diffing strategies."""

from __future__ import annotations

import pytest

from watchtower.diffs.items import ItemDiff
from watchtower.diffs.text import TextDiff
from watchtower.models import Change, ChangeKind, Item, Snapshot
from watchtower.registry import create_differ


def test_text_diff_first_run_returns_empty() -> None:
    """Test that when old snapshot is None (ADR-004), no changes are reported."""
    differ = TextDiff()
    new_snapshot = Snapshot(raw_text="Line 1\nLine 2\n")

    changes = differ.diff(old=None, new=new_snapshot)
    assert changes == []


def test_text_diff_identical_snapshots_return_empty() -> None:
    """Test that unchanged raw text yields no changes."""
    differ = TextDiff()
    old_snap = Snapshot(raw_text="Same text\n")
    new_snap = Snapshot(raw_text="Same text\n")

    changes = differ.diff(old=old_snap, new=new_snap)
    assert changes == []


def test_text_diff_computes_unified_diff() -> None:
    """Test that differences in text produce a TEXT Change containing unified diff output."""
    differ = TextDiff()
    old_snap = Snapshot(raw_text="Apple\nBanana\n")
    new_snap = Snapshot(raw_text="Apple\nOrange\n")

    changes = differ.diff(old=old_snap, new=new_snap)
    assert len(changes) == 1
    change = changes[0]
    assert change.kind == ChangeKind.TEXT
    assert change.diff_text is not None
    assert "-Banana" in change.diff_text
    assert "+Orange" in change.diff_text


def test_registry_creates_text_differ() -> None:
    """Test instantiating TextDiff from the plugin registry."""
    differ = create_differ("text", context_lines=5)
    assert isinstance(differ, TextDiff)
    assert differ.context_lines == 5


def _summary(changes: list[Change]) -> list[tuple[ChangeKind, str | None, str | None]]:
    """Reduce changes to (kind, item key, before key) tuples for comparison."""
    return [
        (
            change.kind,
            change.item.key if change.item is not None else None,
            change.before.key if change.before is not None else None,
        )
        for change in changes
    ]


@pytest.mark.parametrize(
    ("old_items", "new_items", "expected"),
    [
        pytest.param(None, (Item(key="1", title="Flat"),), [], id="first-run"),
        pytest.param((), (Item(key="1", title="Flat"),), [(ChangeKind.NEW, "1", None)], id="new"),
        pytest.param(
            (Item(key="1", title="Flat"),), (), [(ChangeKind.REMOVED, "1", None)], id="removed"
        ),
        pytest.param(
            (Item(key="1", title="Flat", price=3000.0),),
            (Item(key="1", title="Flat", price=2800.0),),
            [(ChangeKind.CHANGED, "1", "1")],
            id="changed-price",
        ),
        pytest.param(
            (Item(key="1", title="Old title"),),
            (Item(key="1", title="New title"),),
            [(ChangeKind.CHANGED, "1", "1")],
            id="changed-title",
        ),
        pytest.param(
            (Item(key="1", title="Flat"),),
            (Item(key="1", title="Flat"),),
            [],
            id="unchanged",
        ),
        pytest.param(
            (
                Item(key="a", title="A"),
                Item(key="b", title="B"),
                Item(key="c", title="C"),
            ),
            (
                Item(key="b", title="B changed"),
                Item(key="d", title="D"),
            ),
            [
                (ChangeKind.CHANGED, "b", "b"),
                (ChangeKind.NEW, "d", None),
                (ChangeKind.REMOVED, "a", None),
                (ChangeKind.REMOVED, "c", None),
            ],
            id="mixed",
        ),
    ],
)
def test_item_diff(
    old_items: tuple[Item, ...] | None,
    new_items: tuple[Item, ...],
    expected: list[tuple[ChangeKind, str | None, str | None]],
) -> None:
    """Test new, removed and changed items, plus the first-run baseline."""
    old = None if old_items is None else Snapshot(items=old_items)
    new = Snapshot(items=new_items)

    changes = ItemDiff().diff(old=old, new=new)

    assert _summary(changes) == expected


def test_item_diff_changed_keeps_previous_item_in_before() -> None:
    """Test that a changed item holds both the new and the previous version."""
    before = Item(key="1", title="Flat", price=3000.0)
    after = Item(key="1", title="Flat", price=2800.0)

    changes = ItemDiff().diff(Snapshot(items=(before,)), Snapshot(items=(after,)))

    assert len(changes) == 1
    assert changes[0].kind == ChangeKind.CHANGED
    assert changes[0].item == after
    assert changes[0].before == before


def test_item_diff_ignores_item_order() -> None:
    """Test that reordering a page produces no changes."""
    first = Item(key="a", title="A")
    second = Item(key="b", title="B")

    changes = ItemDiff().diff(Snapshot(items=(first, second)), Snapshot(items=(second, first)))

    assert changes == []


def test_item_diff_collapses_duplicate_keys_to_the_last_item() -> None:
    """Test that a repeated key identifies one item, the last occurrence (ADR-014)."""
    before = Item(key="1", title="Old")
    first = Item(key="1", title="First")
    last = Item(key="1", title="Last")

    changes = ItemDiff().diff(Snapshot(items=(before,)), Snapshot(items=(first, last)))

    assert len(changes) == 1
    assert changes[0].kind == ChangeKind.CHANGED
    assert changes[0].item == last
    assert changes[0].before == before
