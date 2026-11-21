"""Tests for the formatting shared by notifiers."""

from __future__ import annotations

from watchtower import Change, ChangeKind, Item
from watchtower.notifiers._format import change_text, item_line


def test_change_text_covers_diff_item_and_bare_kind() -> None:
    """The shared formatter handles every kind of change."""
    assert change_text(Change(kind=ChangeKind.TEXT, diff_text="-old\n+new\n")) == (
        "--- Diff ---\n-old\n+new"
    )
    assert change_text(Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat"))) == (
        "New: Flat"
    )
    assert change_text(Change(kind=ChangeKind.REMOVED)) == "Removed"


def test_item_line_is_public_and_formats_prices() -> None:
    """Item lines can be built directly and show the old and new prices."""
    line = item_line(
        ChangeKind.CHANGED,
        Item(key="1", title="Flat", price=2600.0),
        Item(key="1", title="Old flat", price=2800.0),
    )

    assert line == "Changed: Flat, 2 800 zł → 2 600 zł (was: Old flat)"
