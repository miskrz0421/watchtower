"""Diffing strategies for detecting changes between snapshots."""

from watchtower.diffs.base import Differ
from watchtower.diffs.text import TextDiff

__all__ = ["Differ", "TextDiff"]
