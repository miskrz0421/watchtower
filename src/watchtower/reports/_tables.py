"""pandas tables computed from the history."""

from __future__ import annotations

import pandas as pd

from watchtower.storage._history import HistoryStore


def changes_per_week(history: HistoryStore) -> pd.DataFrame:
    """Count the reported changes of every watcher per week.

    Args:
        history: History to read.

    Returns:
        One row per week and one column per watcher.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError


def failure_rate(history: HistoryStore) -> pd.DataFrame:
    """Compute how many checks of every watcher failed.

    Args:
        history: History to read.

    Returns:
        One row per watcher with its number of checks and the share that failed.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError


def price_trend(history: HistoryStore, watcher_name: str, key: str) -> pd.DataFrame:
    """Follow the price of one item over time.

    Args:
        history: History to read.
        watcher_name: Watcher that reported the item.
        key: Key of the item.

    Returns:
        One row per reported price, oldest first.

    Raises:
        StorageError: If the history cannot be read.
    """
    raise NotImplementedError
