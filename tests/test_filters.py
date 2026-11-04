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
