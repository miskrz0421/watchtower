"""FakeSource for testing pipelines with predetermined snapshots or contents."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from watchtower.models import Item, Snapshot
from watchtower.registry import register_source
from watchtower.sources.base import Source


@register_source("fake")
class FakeSource(Source):
    """Source returning a scripted sequence of snapshots or raw text contents.

    Useful for offline testing, demos, and reproducibility. If the calls exceed
    the number of scripted entries, the last entry is repeated.
    """

    def __init__(
        self,
        snapshots: Sequence[Snapshot] | None = None,
        contents: Sequence[str] | None = None,
    ) -> None:
        """Initialize FakeSource with either snapshots or raw string contents.

        Args:
            snapshots: Optional list of pre-constructed Snapshot instances.
            contents: Optional list of raw text strings.
        """
        self._step = 0
        if snapshots is not None:
            self._snapshots = list(snapshots)
        elif contents is not None:
            self._snapshots = [
                Snapshot(items=(), raw_text=text, taken_at=datetime.now(UTC))
                for text in contents
            ]
        else:
            self._snapshots = [Snapshot(items=(), raw_text="", taken_at=datetime.now(UTC))]

    def fetch(self) -> str:
        """Return raw content of the current scripted snapshot."""
        current = self._get_current_snapshot()
        return current.raw_text

    def parse(self, raw: str) -> Iterable[Item]:
        """Return the items of the current scripted snapshot."""
        current = self._get_current_snapshot()
        return current.items

    def snapshot(self) -> Snapshot:
        """Advance the step counter and return the snapshot via template method."""
        snap = super().snapshot()
        if self._step < len(self._snapshots) - 1:
            self._step += 1
        return snap

    def _get_current_snapshot(self) -> Snapshot:
        """Retrieve the snapshot for the current step."""
        idx = min(self._step, len(self._snapshots) - 1)
        return self._snapshots[idx]
