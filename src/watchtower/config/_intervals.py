"""Reading intervals written as text, such as `15m`."""

from __future__ import annotations

import re
from datetime import timedelta

from watchtower._errors import ConfigError

_INTERVAL_PATTERN = re.compile(r"(\d+)([smhd])")
_UNIT_MAP = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}


def parse_interval(text: str) -> timedelta:
    """Convert interval text to a timedelta.

    The text is a whole number followed by a unit: `s` (seconds), `m`
    (minutes), `h` (hours) or `d` (days), as in `30s`, `15m`, `2h`, `1d`.

    Args:
        text: Interval as written in a config file.

    Returns:
        The interval as a timedelta.

    Raises:
        ConfigError: If the text is not a number and a unit, or is not positive,
            or represents an interval that is too long.
    """
    if not isinstance(text, str):
        msg = f"Interval must be text, got {text!r}"
        raise ConfigError(msg)
    match = _INTERVAL_PATTERN.fullmatch(text)
    if match is None:
        msg = (
            f"Invalid interval {text!r}; "
            "expected a positive whole number followed by s, m, h or d (such as '15m')"
        )
        raise ConfigError(msg)
    value_str, unit = match.groups()
    value = int(value_str)
    if value <= 0:
        msg = f"Interval must be positive, got {text!r}"
        raise ConfigError(msg)
    keyword = _UNIT_MAP[unit]
    try:
        return timedelta(**{keyword: value})
    except OverflowError as err:
        msg = f"Interval {text!r} is too long"
        raise ConfigError(msg) from err
