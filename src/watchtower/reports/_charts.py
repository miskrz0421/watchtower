"""matplotlib charts of the report tables."""

from __future__ import annotations

from pathlib import Path

from watchtower.storage._history import HistoryStore


def save_charts(history: HistoryStore, out_dir: Path) -> list[Path]:
    """Draw every report as a PNG file.

    Args:
        history: History to read.
        out_dir: Folder for the files; created if missing.

    Returns:
        The paths of the saved files.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError
