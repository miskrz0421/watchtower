"""Reading intervals written as text, such as `15m`."""

from __future__ import annotations

from datetime import timedelta


def parse_interval(text: str) -> timedelta:
    """Convert interval text to a timedelta.

    The text is a whole number followed by a unit: `s` (seconds), `m`
    (minutes), `h` (hours) or `d` (days), as in `30s`, `15m`, `2h`, `1d`.

    Args:
        text: Interval as written in a config file.

    Returns:
        The interval as a timedelta.

    Raises:
        ConfigError: If the text is not a number and a unit, or is not positive.
    """
    raise NotImplementedError
