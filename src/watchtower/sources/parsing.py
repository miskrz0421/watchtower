"""Helpers for extracting values from scraped text."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def parse_price(text: str) -> float | None:
    """Extract a price from text such as `2 999 zł`.

    Thousands may be separated by spaces (including non-breaking spaces),
    dots or commas. A single dot or comma followed by one or two digits is
    treated as a decimal separator.

    Args:
        text: Text containing a price.

    Returns:
        The price as a float, or None if the text contains no price.
    """
    compact = _WHITESPACE.sub("", text)
    match = _NUMBER.search(compact)
    if match is None:
        return None
    return _to_float(match.group())


def _to_float(number: str) -> float:
    """Convert a numeric string with grouping or decimal separators to a float."""
    if "," in number and "." in number:
        decimal = "," if number.rfind(",") > number.rfind(".") else "."
        grouping = "." if decimal == "," else ","
        number = number.replace(grouping, "").replace(decimal, ".")
    elif "," in number:
        number = _normalize_single_separator(number, ",")
    elif "." in number:
        number = _normalize_single_separator(number, ".")
    return float(number)


def _normalize_single_separator(number: str, separator: str) -> str:
    """Decide whether the only separator in a number groups thousands or starts decimals."""
    parts = number.split(separator)
    if len(parts) > 2 or len(parts[1]) == 3:
        return "".join(parts)
    return f"{parts[0]}.{parts[1]}"
