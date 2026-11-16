"""Filters deciding which detected changes matter."""

from watchtower.filters._base import And, Filter, Not, Or
from watchtower.filters._builtin import (
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
