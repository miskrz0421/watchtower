"""FakeSource for testing pipelines with predetermined snapshots or contents."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from watchtower.models import Item, Snapshot
from watchtower.registry import register_source
from watchtower.sources.base import Source


@register_source("fake")
class FakeSource(Source):
    """Source replaying a scripted sequence of snapshots or raw text contents.

    Useful for offline testing, demos, and reproducibility. Each check replays
    the items and raw text of the next entry, and `taken_at` is the real time
    of the check. If the calls exceed the scripted entries, the last entry is
    repeated.
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
        if snapshots is not None:
            self._snapshots = list(snapshots)
        elif contents is not None:
            self._snapshots = [Snapshot(raw_text=text) for text in contents]
        else:
            self._snapshots = [Snapshot()]
        self._step = 0
        self._current_items: tuple[Item, ...] = ()

    def fetch(self) -> str:
        """Return the raw text of the next scripted entry."""
        current = self._snapshots[self._step]
        self._current_items = current.items
        self._step = min(self._step + 1, len(self._snapshots) - 1)
        return current.raw_text

    def parse(self, raw: str) -> Iterable[Item]:
        """Return the items of the entry selected by the last `fetch()`."""
        return self._current_items
