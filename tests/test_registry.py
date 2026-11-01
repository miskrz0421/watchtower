"""Tests for the plugin registry."""

from __future__ import annotations

import pytest

from watchtower.diffs.text import TextDiff
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.registry import (
    create,
    create_differ,
    create_notifier,
    create_source,
    list_plugins,
    register_differ,
    register_filter,
    register_notifier,
    register_source,
)
from watchtower.sources.fake import FakeSource


def test_registry_registration_and_creation() -> None:
    """Test registering classes with decorators and creating instances with parameters."""

    @register_source("dummy_src")
    class DummySource:
        def __init__(self, greeting: str) -> None:
            self.greeting = greeting

    @register_differ("dummy_diff")
    class DummyDiffer:
        def __init__(self, mode: str = "fast") -> None:
            self.mode = mode

    @register_filter("dummy_filt")
    class DummyFilter:
        pass

    @register_notifier("dummy_notify")
    class DummyNotifier:
        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint

    src = create("source", "dummy_src", greeting="hello")
    assert isinstance(src, DummySource)
    assert src.greeting == "hello"

    diff = create("differ", "dummy_diff")
    assert isinstance(diff, DummyDiffer)
    assert diff.mode == "fast"

    plugins = list_plugins()
    assert "dummy_src" in plugins["source"]
    assert "dummy_diff" in plugins["differ"]
    assert "dummy_filt" in plugins["filter"]
    assert "dummy_notify" in plugins["notifier"]


def test_registry_unknown_kind_and_name_errors() -> None:
    """Test that requesting nonexistent kinds or plugins raises KeyError."""
    with pytest.raises(KeyError, match="Unknown plugin kind"):
        create("unknown_kind", "anything")

    with pytest.raises(KeyError, match="Unknown source plugin"):
        create("source", "nonexistent_source")


def test_typed_factory_create_source() -> None:
    """Test create_source returns a properly typed Source instance."""
    source = create_source("fake", contents=["step 1"])
    assert isinstance(source, FakeSource)


def test_typed_factory_create_differ() -> None:
    """Test create_differ returns a properly typed Differ instance."""
    differ = create_differ("text", context_lines=5)
    assert isinstance(differ, TextDiff)


def test_typed_factory_create_notifier() -> None:
    """Test create_notifier returns a properly typed Notifier instance."""
    notifier = create_notifier("console")
    assert isinstance(notifier, ConsoleNotifier)
