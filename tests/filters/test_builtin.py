"""Tests for built-in filters."""

from __future__ import annotations

import pytest

from watchtower import Change, ChangeKind, Item, create_filter
from watchtower.filters import (
    KindIs,
    Matches,
    NewItems,
    PriceAbove,
    PriceBelow,
    TextContains,
)


def test_new_items_created_via_registry_without_arguments() -> None:
    """Test that NewItems (the only no-argument filter) is created via create_filter."""
    created = create_filter("new_items")

    assert isinstance(created, NewItems)
    assert created.matches(Change(kind=ChangeKind.NEW))
    assert not created.matches(Change(kind=ChangeKind.REMOVED))
    assert not created.matches(Change(kind=ChangeKind.CHANGED))
    assert not created.matches(Change(kind=ChangeKind.TEXT))


def test_price_below_created_with_positional_argument() -> None:
    """Test that PriceBelow is created via create_filter with a positional arg.

    Config entries such as `price_below: 3000` pass the value positionally.
    """
    created = create_filter("price_below", 3000)

    assert isinstance(created, PriceBelow)
    cheap = Item(key="k1", title="t", price=19.99)
    assert created.matches(Change(kind=ChangeKind.CHANGED, item=cheap))
    just_below = Item(key="k1", title="t", price=2999.99)
    assert created.matches(Change(kind=ChangeKind.CHANGED, item=just_below))
    at_limit = Item(key="k1", title="t", price=3000)
    assert not created.matches(Change(kind=ChangeKind.CHANGED, item=at_limit))
    above = Item(key="k1", title="t", price=4000)
    assert not created.matches(Change(kind=ChangeKind.CHANGED, item=above))
    assert not created.matches(Change(kind=ChangeKind.REMOVED))  # no item
    no_price = Item(key="k1", title="t")
    assert not created.matches(Change(kind=ChangeKind.CHANGED, item=no_price))  # no price


def test_price_above() -> None:
    """Test PriceAbove matches changes whose item costs more than the limit."""
    f = PriceAbove(50)

    above = Item(key="k1", title="t", price=99.99)
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=above))
    at_limit = Item(key="k1", title="t", price=50)
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=at_limit))
    below = Item(key="k1", title="t", price=10)
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=below))
    assert not f.matches(Change(kind=ChangeKind.REMOVED))  # no item
    no_price = Item(key="k1", title="t")
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=no_price))  # no price


@pytest.mark.parametrize("filter_class", [PriceBelow, PriceAbove])
@pytest.mark.parametrize(
    ("limit", "error"),
    [("abc", TypeError), (float("nan"), ValueError), (float("inf"), ValueError)],
)
def test_price_filters_reject_invalid_limit(
    filter_class: type[PriceBelow | PriceAbove], limit: float, error: type[Exception]
) -> None:
    """A limit that is not a finite number is rejected when the filter is created."""
    with pytest.raises(error):
        filter_class(limit)


def test_kind_is() -> None:
    """Test KindIs matches changes of the configured kind."""
    f = KindIs("removed")

    assert f.matches(Change(kind=ChangeKind.REMOVED))
    assert not f.matches(Change(kind=ChangeKind.NEW))
    assert not f.matches(Change(kind=ChangeKind.CHANGED))


def test_kind_is_rejects_unknown_kind() -> None:
    """Test KindIs rejects an unknown kind string."""
    with pytest.raises(ValueError):
        KindIs("nope")


def test_kind_is_created_with_positional_argument() -> None:
    """Test that KindIs is created via create_filter with a positional arg."""
    created = create_filter("kind_is", "removed")

    assert isinstance(created, KindIs)
    assert created.matches(Change(kind=ChangeKind.REMOVED))
    assert not created.matches(Change(kind=ChangeKind.NEW))


def test_text_contains() -> None:
    """Test TextContains matches case-insensitively in the item's title or text."""
    f = TextContains("widget")

    cheap = Item(key="k1", title="Cheap Widget", text="", price=10)
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=cheap))
    upper = Item(key="k1", title="WIDGET", text="")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=upper))
    in_text = Item(key="k1", title="", text="A fine widget here")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=in_text))
    exact = Item(key="k1", title="widget", text="")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=exact))
    no_match = Item(key="k1", title="gadget", text="")
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=no_match))
    assert not f.matches(Change(kind=ChangeKind.REMOVED))  # no item
    empty = Item(key="k1", title="")
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=empty))  # empty title and text


def test_text_contains_does_not_concatenate_title_and_text() -> None:
    """Test TextContains searches title and text separately, not their concatenation."""
    f = TextContains("cheap widget")

    split_across = Item(key="k1", title="cheap", text="widget")
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=split_across))

    together = Item(key="k1", title="cheap widget", text="")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=together))


def test_matches_does_not_concatenate_title_and_text() -> None:
    """Test Matches searches title and text separately, not their concatenation."""
    f = Matches(r"price \$19\.99")

    split_across = Item(key="k1", title="price ", text="$19.99")
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=split_across))

    together = Item(key="k1", title="price $19.99", text="")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=together))


def test_matches() -> None:
    """Test Matches searches the item's title and text with a regular expression."""
    f = Matches(r"\d+\.\d{2}")

    price_title = Item(key="k1", title="Price $19.99", text="")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=price_title))
    price_text = Item(key="k1", title="", text="cost 19.99")
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=price_text))
    no_decimals = Item(key="k1", title="Price 19", text="")
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=no_decimals))
    assert not f.matches(Change(kind=ChangeKind.REMOVED))  # no item

    with pytest.raises(ValueError):
        Matches("[")
