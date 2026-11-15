"""Filters deciding which detected changes matter."""

from watchtower.filters.base import And, Filter, Not, Or
from watchtower.filters.builtin import (
    KindIs,
    Matches,
    NewItems,
    PriceAbove,
    PriceBelow,
    TextContains,
)

__all__ = [
    "And",
    "Filter",
    "KindIs",
    "Matches",
    "NewItems",
    "Not",
    "Or",
    "PriceAbove",
    "PriceBelow",
    "TextContains",
]
