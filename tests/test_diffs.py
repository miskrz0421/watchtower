"""Tests for Diffing strategies."""

from __future__ import annotations

from watchtower.diffs.text import TextDiff
from watchtower.models import ChangeKind, Snapshot
from watchtower.registry import create


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
    differ = create("differ", "text", context_lines=5)
    assert isinstance(differ, TextDiff)
    assert differ.context_lines == 5
