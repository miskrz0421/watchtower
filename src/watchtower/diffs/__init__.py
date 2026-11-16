"""Diffing strategies for detecting changes between snapshots."""

from watchtower.diffs._base import Differ
from watchtower.diffs._items import ItemDiff
from watchtower.diffs._text import TextDiff

__all__ = ["Differ", "ItemDiff", "TextDiff"]
