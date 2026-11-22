"""Shared formatting of change events for notifiers."""

from __future__ import annotations

from watchtower._models import Change, ChangeKind, Item


def change_text(change: Change) -> str:
    """Describe one change: a text diff, an item line, or just the kind of change.

    Args:
        change: Change to describe.

    Returns:
        The text to display, without a trailing newline.
    """
    if change.kind == ChangeKind.TEXT and change.diff_text:
        text = f"--- Diff ---\n{change.diff_text.removesuffix('\n')}"
    elif change.item is not None:
        text = _item_line(change.kind, change.item, change.before)
    else:
        text = change.kind.value.capitalize()
    return text


def truncate(text: str, limit: int) -> str:
    """Cut text to at most `limit` characters, ending with '…' when it was cut.

    Args:
        text: Text to shorten.
        limit: Maximum length of the result.

    Returns:
        The text unchanged if it fits, otherwise its start followed by '…'.
    """
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _item_line(kind: ChangeKind, item: Item, before: Item | None) -> str:
    """Describe an item change in one line, e.g. 'Changed: Flat, 2 800 zł → 2 600 zł'.

    Args:
        kind: Kind of the change.
        item: Item after the change.
        before: Item before the change, for a changed item.

    Returns:
        The line to display.
    """
    line = f"{kind.value.capitalize()}: {item.title}"
    if before is not None and before.price != item.price:
        line += f", {_price(before.price)} → {_price(item.price)}"
    elif item.price is not None:
        line += f", {_price(item.price)}"
    if before is not None and before.title != item.title:
        line += f" (was: {before.title})"
    return line


def _price(price: float | None) -> str:
    """Format a price the Polish way, e.g. '2 800 zł' or '2 400,50 zł'.

    Args:
        price: Price to format, or None.

    Returns:
        The formatted price, or 'no price' for None.
    """
    if price is None:
        return "no price"
    if price.is_integer():
        return f"{int(price):,} zł".replace(",", " ")
    grouped = f"{price:,.2f}"  # '2,400.50'
    return grouped.replace(",", " ").replace(".", ",") + " zł"
