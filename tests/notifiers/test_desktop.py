"""Tests for the optional desktop notifier dependency."""

from __future__ import annotations

import pytest

from watchtower import MissingDependencyError, list_plugins
from watchtower.notifiers import DesktopNotifier


def test_desktop_plugin_is_registered_by_import() -> None:
    """Importing watchtower registers the desktop plugin without extra work."""
    assert "desktop" in list_plugins()["notifier"]


def test_desktop_notifier_requires_extra(no_desktop_notifier: None) -> None:
    """A missing desktop-notifier package explains how to install it."""
    with pytest.raises(MissingDependencyError, match=r"watchtower\[desktop\]"):
        DesktopNotifier()
