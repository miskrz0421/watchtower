"""Tests for building filters from configuration specifications."""

from __future__ import annotations

import pytest

from watchtower import Change, ChangeKind, ConfigError, Item
from watchtower.config._filters import build_filter
from watchtower.filters import (
    And,
    NewItems,
    Not,
    Or,
    PriceBelow,
    TextContains,
)


def test_build_named_filter_from_string() -> None:
    """Test building a registered filter by its name string."""
    filt = build_filter("Watcher1", "new_items")
    assert isinstance(filt, NewItems)


def test_build_filter_with_parameter_mapping() -> None:
    """Test building a parameterized filter from a single-key mapping."""
    filt = build_filter("Watcher1", {"price_below": 2500})
    assert isinstance(filt, PriceBelow)

    cheap = Change(kind=ChangeKind.NEW, item=Item(key="1", title="Cheap", price=2000))
    expensive = Change(kind=ChangeKind.NEW, item=Item(key="2", title="Expensive", price=3000))
    assert filt.matches(cheap)
    assert not filt.matches(expensive)

    filt_text = build_filter("Watcher1", {"text_contains": "keyword"})
    assert isinstance(filt_text, TextContains)


def test_build_composite_all_filter() -> None:
    """Test building an 'all' composite filter."""
    filt = build_filter("Watcher1", {"all": ["new_items", {"price_below": 2500}]})
    assert isinstance(filt, And)
    cheap_new = Change(kind=ChangeKind.NEW, item=Item(key="1", title="Cheap", price=2000))
    cheap_changed = Change(kind=ChangeKind.CHANGED, item=Item(key="2", title="Cheap", price=2000))
    assert filt.matches(cheap_new)
    assert not filt.matches(cheap_changed)


def test_build_composite_any_filter() -> None:
    """Test building an 'any' composite filter."""
    filt = build_filter(
        "Watcher1",
        {"any": [{"price_below": 2000}, {"text_contains": "urgent"}]},
    )
    assert isinstance(filt, Or)
    cheap = Change(kind=ChangeKind.NEW, item=Item(key="1", title="Flat", price=1500))
    urgent = Change(kind=ChangeKind.NEW, item=Item(key="2", title="urgent flat", price=3500))
    unrelated = Change(kind=ChangeKind.NEW, item=Item(key="3", title="Normal", price=3500))
    assert filt.matches(cheap)
    assert filt.matches(urgent)
    assert not filt.matches(unrelated)


def test_build_composite_not_filter() -> None:
    """Test building a 'not' composite filter from either a single item or a 1-item list."""
    filt_direct = build_filter("Watcher1", {"not": "new_items"})
    assert isinstance(filt_direct, Not)
    assert not filt_direct.matches(Change(kind=ChangeKind.NEW))
    assert filt_direct.matches(Change(kind=ChangeKind.REMOVED))

    filt_list = build_filter("Watcher1", {"not": ["new_items"]})
    assert isinstance(filt_list, Not)
    assert not filt_list.matches(Change(kind=ChangeKind.NEW))
    assert filt_list.matches(Change(kind=ChangeKind.REMOVED))


def test_build_nested_composite_filters() -> None:
    """Test building deeply nested composite filters."""
    spec = {
        "all": [
            "new_items",
            {"any": [{"price_below": 2000}, {"price_above": 6000}]},
            {"not": {"text_contains": "quiet"}},
        ]
    }
    filt = build_filter("Watcher1", spec)
    assert isinstance(filt, And)

    matching = Change(
        kind=ChangeKind.NEW,
        item=Item(key="1", title="special flat", price=1500),
    )
    quiet = Change(
        kind=ChangeKind.NEW,
        item=Item(key="2", title="special quiet flat", price=1500),
    )
    not_new = Change(
        kind=ChangeKind.CHANGED,
        item=Item(key="3", title="special flat", price=1500),
    )
    assert filt.matches(matching)
    assert not filt.matches(quiet)
    assert not filt.matches(not_new)


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        (12345, "filter entry must be a name or mapping, got 12345"),
        (["not_allowed"], "filter entry must be a name or mapping"),
        ("unknown_filter", "unknown filter 'unknown_filter'"),
        ({"unknown_plugin": 123}, "unknown filter 'unknown_plugin'"),
        ({"a": 1, "b": 2}, "filter entry must have exactly one key"),
        ({123: "val"}, "filter name must be a string"),
        ("price_below", "filter 'price_below'"),
        ({"kind_is": "invalid_kind"}, "filter 'kind_is'"),
        ({"matches": "[unclosed regex"}, "filter 'matches'"),
        ({"all": "not_a_list"}, "'all' requires a list of filters"),
        ({"all": []}, "'all' requires at least one filter"),
        ({"any": 42}, "'any' requires a list of filters"),
        ({"any": []}, "'any' requires at least one filter"),
        ({"not": []}, "'not' requires exactly one filter"),
        ({"not": ["new_items", "new_items"]}, "'not' requires exactly one filter"),
    ],
)
def test_build_filter_invalid_spec_raises_config_error(entry: object, match: str) -> None:
    """Test that invalid filter specifications raise ConfigError with clear messages."""
    with pytest.raises(ConfigError, match=match):
        build_filter("Watcher1", entry)
