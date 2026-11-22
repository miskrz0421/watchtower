"""Shared formatting for GUI widgets."""

from __future__ import annotations

from datetime import datetime

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_time(timestamp: datetime) -> str:
    """Return a timestamp formatted in the local timezone.

    Args:
        timestamp: Datetime to display.

    Returns:
        Date and time in the format used by the Watchers and Changes tables.
    """
    return timestamp.astimezone().strftime(_TIME_FORMAT)
