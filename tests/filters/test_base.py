"""Tests for the Filter base class and composite filters."""

from __future__ import annotations

import pytest

from watchtower import Change, ChangeKind, Item, create_filter, register_filter
from watchtower.filters import And, Filter, NewItems, Or, PriceAbove, PriceBelow, TextContains


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


@pytest.mark.parametrize("composite", [And, Or])
def test_composite_rejects_zero_filters(composite: type[And | Or]) -> None:
    """Test And and Or reject being constructed with no filters."""
    with pytest.raises(ValueError, match="At least one filter is required"):
        composite()


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
