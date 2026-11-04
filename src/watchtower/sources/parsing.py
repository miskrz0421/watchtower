"""Helpers for extracting values from scraped text."""

from __future__ import annotations


def parse_price(text: str) -> float | None:
    """Extract a price from text such as `2 999 zł`.

    Args:
        text: Text containing a price.

    Returns:
        The price as a float, or None if the text contains no price.
    """
    raise NotImplementedError
