"""Helpers for extracting values from scraped text."""

from __future__ import annotations

import re

# A space (also a non-breaking one) between digits that is followed by exactly
# three digits groups thousands, as in "2 999"; other spaces separate numbers.
_THOUSANDS_SPACE = re.compile(r"(?<=\d)\s(?=\d{3}(?!\d))")
_NUMBER = r"\d+(?:[.,]\d+)*"
_CURRENCY = r"(?:zł|zl|pln|eur|usd|gbp)(?![^\W\d_])|[€$£]"
_NUMBER_BEFORE_CURRENCY = re.compile(rf"({_NUMBER})\s*(?:{_CURRENCY})", re.IGNORECASE)
_NUMBER_AFTER_CURRENCY = re.compile(rf"(?:{_CURRENCY})\s*({_NUMBER})", re.IGNORECASE)
_ANY_NUMBER = re.compile(_NUMBER)


def parse_price(text: str) -> float | None:
    """Extract a price from text such as `2 999 zł`.

    Thousands may be separated by spaces (including non-breaking spaces),
    dots or commas. A single dot or comma followed by one or two digits is
    treated as a decimal separator.

    When the text holds several numbers, as in `2 rooms, 45 m², 2 800 zł`,
    the first number written next to a currency (zł, PLN, €, EUR, $, USD,
    £, GBP) is the price. Without a currency, the first number is used.

    Args:
        text: Text containing a price.

    Returns:
        The price as a float, or None if the text contains no price.
    """
    compact = _THOUSANDS_SPACE.sub("", text)
    with_currency = [
        match
        for match in (
            _NUMBER_BEFORE_CURRENCY.search(compact),
            _NUMBER_AFTER_CURRENCY.search(compact),
        )
        if match is not None
    ]
    if with_currency:
        first = min(with_currency, key=lambda match: match.start())
        return _to_float(first.group(1))
    match = _ANY_NUMBER.search(compact)
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
