"""Tests for the public API of the watchtower package."""

from __future__ import annotations

import watchtower


def test_every_public_name_exists() -> None:
    """Test that each name listed in __all__ can be imported from the package."""
    missing = [name for name in watchtower.__all__ if not hasattr(watchtower, name)]

    assert missing == []


def test_importing_the_package_registers_built_in_plugins() -> None:
    """Test that `import watchtower` alone makes the built-in plugins creatable by name."""
    plugins = watchtower.list_plugins()

    assert {"fake", "file", "rss", "webpage"} <= set(plugins["source"])
    assert {"items", "text"} <= set(plugins["differ"])
    assert "console" in plugins["notifier"]
