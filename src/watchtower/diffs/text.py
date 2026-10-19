"""Line-by-line textual differ using Python standard difflib."""

from __future__ import annotations

import difflib

from watchtower.diffs.base import Differ
from watchtower.models import Change, ChangeKind, Snapshot
from watchtower.registry import register_differ


@register_differ("text")
class TextDiff(Differ):
    """Computes unified line-based diffs between raw snapshot texts."""

    def __init__(self, context_lines: int = 3) -> None:
        """Initialize TextDiff.

        Args:
            context_lines: Number of surrounding context lines in unified diff.
        """
        self.context_lines = context_lines

    def diff(self, old: Snapshot | None, new: Snapshot) -> list[Change]:
        """Compute textual unified diff between old and new snapshot texts.

        Returns an empty list if old is None (first run/baseline) or if
        raw texts are identical.

        Args:
            old: The previous snapshot, or None if first run.
            new: The current snapshot.

        Returns:
            A list containing a Change of kind TEXT, or an empty list if no diff.
        """
        if old is None or old.raw_text == new.raw_text:
            return []

        diff_lines = list(
            difflib.unified_diff(
                old.raw_text.splitlines(keepends=True),
                new.raw_text.splitlines(keepends=True),
                fromfile="previous",
                tofile="current",
                n=self.context_lines,
            )
        )

        if not diff_lines:
            return []

        diff_str = "".join(diff_lines)
        return [Change(kind=ChangeKind.TEXT, diff_text=diff_str)]
