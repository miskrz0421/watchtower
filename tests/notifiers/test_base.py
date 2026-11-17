"""Tests for the base Notifier interface."""

from __future__ import annotations

import pytest

from watchtower.notifiers import Notifier


def test_notifier_cannot_be_instantiated_directly() -> None:
    """Test that Notifier is abstract and requires send()."""
    with pytest.raises(TypeError):
        Notifier()  # type: ignore[abstract]
