"""Tests for the Filter base class."""

from __future__ import annotations

import pytest

from watchtower.filters.base import Filter
from watchtower.models import Change, ChangeKind
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


def test_filter_can_be_created_with_a_positional_argument() -> None:
    """Test that create_filter passes positional arguments, as `price_below: 3000` needs."""

    @register_filter("kind_is")
    class KindIs(Filter):
        """Filter keeping changes of one kind."""

        def __init__(self, kind: str) -> None:
            """Remember the kind to keep."""
            self._kind = ChangeKind(kind)

        def matches(self, change: Change) -> bool:
            """Accept a change of the remembered kind."""
            return change.kind == self._kind

    created = create_filter("kind_is", "removed")

    assert created.matches(Change(kind=ChangeKind.REMOVED))
    assert not created.matches(Change(kind=ChangeKind.NEW))
