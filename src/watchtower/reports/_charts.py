"""matplotlib charts of the report tables."""

from __future__ import annotations

from pathlib import Path

from matplotlib.figure import Figure

from watchtower.storage._history import HistoryStore


def changes_figure(history: HistoryStore) -> Figure:
    """Draw how many changes every watcher reported per week.

    Args:
        history: History to read.

    Returns:
        The chart; with an empty history it says that there is no data yet.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError


def failure_figure(history: HistoryStore) -> Figure:
    """Draw the share of failed checks of every watcher.

    Args:
        history: History to read.

    Returns:
        The chart; with an empty history it says that there is no data yet.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError


def price_figure(history: HistoryStore, watcher_name: str) -> Figure:
    """Draw the price of every item of one watcher over time.

    Args:
        history: History to read.
        watcher_name: Watcher whose items are drawn.

    Returns:
        The chart; a watcher without prices gets one that says so.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError


def save_charts(history: HistoryStore, out_dir: Path) -> list[Path]:
    """Save every chart as a PNG file.

    Args:
        history: History to read.
        out_dir: Folder for the files; created if missing.

    Returns:
        The paths of the saved files.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError
