"""Tests for the public API of the watchtower packages."""

from __future__ import annotations

from types import ModuleType

import pytest

import watchtower
from watchtower import config, core, diffs, filters, notifiers, sources, storage

_PACKAGES = [watchtower, config, core, diffs, filters, notifiers, sources, storage]


@pytest.mark.parametrize("package", _PACKAGES, ids=lambda package: package.__name__)
def test_every_public_name_exists(package: ModuleType) -> None:
    """Test that each name listed in a package's __all__ can be imported from it."""
    missing = [name for name in package.__all__ if not hasattr(package, name)]

    assert missing == []


def test_importing_the_package_registers_built_in_plugins() -> None:
    """Test that `import watchtower` alone makes the built-in plugins creatable by name."""
    plugins = watchtower.list_plugins()

    assert {"fake", "file", "rss", "webpage", "json_api"} <= set(plugins["source"])
    assert {"items", "text"} <= set(plugins["differ"])
    assert {"new_items", "price_below", "all", "any", "not"} <= set(plugins["filter"])
    assert "console" in plugins["notifier"]
