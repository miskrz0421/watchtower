"""Tests for the formatting shared by notifiers."""

from __future__ import annotations

from watchtower import Change, ChangeKind, Item
from watchtower.notifiers._format import change_text, truncate


def test_change_text_covers_diff_item_and_bare_kind() -> None:
    """The shared formatter handles every kind of change."""
    assert change_text(Change(kind=ChangeKind.TEXT, diff_text="-old\n+new\n")) == (
        "--- Diff ---\n-old\n+new"
    )
    assert change_text(Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat"))) == (
        "New: Flat"
    )
    assert change_text(Change(kind=ChangeKind.REMOVED)) == "Removed"


def test_change_text_shows_old_and_new_price_and_title() -> None:
    """A changed item shows both prices and its previous title."""
    change = Change(
        kind=ChangeKind.CHANGED,
        item=Item(key="1", title="Flat", price=2600.0),
        before=Item(key="1", title="Old flat", price=2800.0),
    )

    assert change_text(change) == "Changed: Flat, 2 800 zł → 2 600 zł (was: Old flat)"


def test_truncate_keeps_short_text() -> None:
    """Text that fits the limit is returned unchanged."""
    assert truncate("abc", 3) == "abc"


def test_truncate_cuts_long_text_with_ellipsis() -> None:
    """Text over the limit is cut to exactly the limit, ending with an ellipsis."""
    assert truncate("abcdef", 4) == "abc…"
