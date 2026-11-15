"""Tests for the Filter base class and built-in filters."""

from __future__ import annotations

import pytest

from watchtower.filters import (
    And,
    Filter,
    KindIs,
    Matches,
    NewItems,
    Or,
    PriceAbove,
    PriceBelow,
    TextContains,
)
from watchtower.models import Change, ChangeKind, Item
from watchtower.registry import create_filter, register_filter


def test_filter_cannot_be_instantiated_directly() -> None:
    """Test that Filter is abstract and requires matches()."""
    with pytest.raises(TypeError):
        Filter()  # type: ignore[abstract]


def test_registered_filter_is_created_and_evaluates_changes() -> None:
    """Test that a Filter subclass works through the plugin registry."""

    @register_filter("only_text")
    class OnlyText(Filter):
        def matches(self, change: Change) -> bool:
            return change.kind == ChangeKind.TEXT

    created = create_filter("only_text")

    assert isinstance(created, Filter)
    assert created.matches(Change(kind=ChangeKind.TEXT, diff_text="+x"))
    assert not created.matches(Change(kind=ChangeKind.REMOVED))


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


def test_kind_is() -> None:
    """Test KindIs matches changes of the configured kind."""
    f = KindIs("removed")

    assert f.matches(Change(kind=ChangeKind.REMOVED))
    assert not f.matches(Change(kind=ChangeKind.NEW))
    assert not f.matches(Change(kind=ChangeKind.CHANGED))


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


def test_and_with_one_and_many_filters() -> None:
    """Test And accepts exactly one filter and more than two filters."""
    one = And(PriceBelow(100))
    many = And(PriceBelow(100), TextContains("widget"), NewItems())

    cheap_widget = Item(key="k1", title="Cheap Widget", text="", price=50)
    assert one.matches(Change(kind=ChangeKind.CHANGED, item=cheap_widget))
    new_cheap_widget = Change(kind=ChangeKind.NEW, item=cheap_widget)
    assert many.matches(new_cheap_widget)

    expensive_widget = Item(key="k1", title="Expensive Widget", text="", price=200)
    assert not many.matches(Change(kind=ChangeKind.NEW, item=expensive_widget))
    cheap_gadget = Item(key="k1", title="Cheap Gadget", text="", price=50)
    assert not many.matches(Change(kind=ChangeKind.NEW, item=cheap_gadget))
    assert not many.matches(Change(kind=ChangeKind.CHANGED, item=cheap_widget))


def test_or_with_one_and_many_filters() -> None:
    """Test Or accepts exactly one filter and more than two filters."""
    one = Or(PriceBelow(100))
    many = Or(PriceBelow(100), PriceAbove(1000), NewItems())

    cheap = Item(key="k1", title="t", price=50)
    assert one.matches(Change(kind=ChangeKind.CHANGED, item=cheap))
    assert many.matches(Change(kind=ChangeKind.CHANGED, item=cheap))

    pricey = Item(key="k1", title="t", price=2000)
    assert many.matches(Change(kind=ChangeKind.CHANGED, item=pricey))

    mid = Item(key="k1", title="t", price=500)
    assert not many.matches(Change(kind=ChangeKind.CHANGED, item=mid))


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


def test_and() -> None:
    """Test And accepts a change only when every inner filter accepts it."""
    f = PriceBelow(100) & TextContains("widget")

    cheap_widget = Item(key="k1", title="Cheap Widget", text="", price=50)
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=cheap_widget))
    expensive = Item(key="k1", title="Expensive Widget", text="", price=200)
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=expensive))
    cheap_gadget = Item(key="k1", title="Cheap Gadget", text="", price=50)
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=cheap_gadget))
    assert not f.matches(Change(kind=ChangeKind.REMOVED))  # no item


def test_or() -> None:
    """Test Or accepts a change when at least one inner filter accepts it."""
    f = PriceBelow(100) | PriceAbove(1000)

    cheap = Item(key="k1", title="t", price=50)
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=cheap))
    pricey = Item(key="k1", title="t", price=2000)
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=pricey))
    mid = Item(key="k1", title="t", price=500)
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=mid))


def test_not() -> None:
    """Test Not accepts a change that the inner filter rejects."""
    f = ~NewItems()

    assert f.matches(Change(kind=ChangeKind.REMOVED))
    assert f.matches(Change(kind=ChangeKind.CHANGED))
    assert not f.matches(Change(kind=ChangeKind.NEW))


def test_composite_filters_nest() -> None:
    """Test that composite filters combine into nested trees."""
    f = (PriceAbove(10) & TextContains("thing")) | NewItems()

    pricey_thing = Item(key="k1", title="Pricey Thing", price=999)
    assert f.matches(Change(kind=ChangeKind.CHANGED, item=pricey_thing))
    assert f.matches(Change(kind=ChangeKind.NEW))
    cheap_thing = Item(key="k1", title="Cheap Thing", price=5)
    assert not f.matches(Change(kind=ChangeKind.CHANGED, item=cheap_thing))
