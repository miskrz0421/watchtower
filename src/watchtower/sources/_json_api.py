"""JSONAPISource for monitoring a list of objects returned by a JSON API."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

import httpx

from watchtower._errors import ParseError
from watchtower._http import DEFAULT_TIMEOUT_SECONDS
from watchtower._models import Item
from watchtower._registry import register_source
from watchtower.sources._http import HttpSource
from watchtower.sources._parsing import non_empty_string, parse_price

type _JsonValue = None | bool | int | float | str | list[_JsonValue] | dict[str, _JsonValue]


@register_source("json_api")
class JSONAPISource(HttpSource):
    """Source producing one Item per object in a JSON list."""

    def __init__(
        self,
        url: str,
        *,
        items_path: str | None = None,
        key_field: str = "id",
        title_field: str = "title",
        url_field: str | None = None,
        price_field: str | None = None,
        text_field: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize JSONAPISource.

        Args:
            url: Address of the API endpoint.
            items_path: Dot-separated path to the list inside the response,
                such as `data.offers`; None means the response is the list.
            key_field: Field holding the stable id of an object.
            title_field: Field holding the title.
            url_field: Field holding a link; None means Items have no url.
            price_field: Field holding the price; None means Items have no price.
            text_field: Field holding a description; None means empty text.
            timeout: Request timeout in seconds.
            transport: Optional transport used by tests.
        """
        super().__init__(url, timeout=timeout, transport=transport)
        self._items_path = (
            [] if items_path is None or items_path.strip() == "" else items_path.split(".")
        )
        self._key_field = key_field
        self._title_field = title_field
        self._url_field = url_field
        self._price_field = price_field
        self._text_field = text_field

    def parse(self, raw: str) -> Iterable[Item]:
        """Parse a JSON response into Items.

        Args:
            raw: JSON text returned by `fetch()`.

        Returns:
            An iterable of Items, one per object in the list.

        Raises:
            ParseError: If the text is not JSON, the path does not lead to a
                list, or an object lacks its key or title.
        """
        try:
            payload: _JsonValue = json.loads(raw)
        except json.JSONDecodeError as err:
            msg = f"Response is not valid JSON: {err}"
            raise ParseError(msg) from err
        return [
            self._to_item(raw_item, position)
            for position, raw_item in enumerate(self._items(payload), start=1)
        ]

    def _items(self, payload: _JsonValue) -> list[_JsonValue]:
        """Return the list of objects at the configured path in the response.

        Args:
            payload: Parsed JSON document.

        Returns:
            The list of objects to turn into Items.

        Raises:
            ParseError: If the path does not exist in the response or does
                not lead to a list.
        """
        for part in self._items_path:
            if not isinstance(payload, Mapping) or part not in payload:
                msg = f"Path {'.'.join(self._items_path)!r} does not exist in the response"
                raise ParseError(msg)
            payload = payload[part]
        if not isinstance(payload, list):
            msg = (
                "Response is not a JSON list"
                if len(self._items_path) == 0
                else f"Path {'.'.join(self._items_path)!r} does not lead to a list"
            )
            raise ParseError(msg)
        return payload

    def _to_item(self, raw_item: _JsonValue, position: int) -> Item:
        """Convert one object from the list to an Item, validating its fields.

        Args:
            raw_item: Object from the list at the configured path.
            position: Number of the object in the list, from 1, for error messages.

        Returns:
            The object as an Item.

        Raises:
            ParseError: If the object is not a JSON object, or has no key or title.
        """
        if not isinstance(raw_item, Mapping):
            msg = f"Object {position} in the list is not a JSON object"
            raise ParseError(msg)

        key = non_empty_string(raw_item.get(self._key_field))
        if key is None:
            msg = f"Object {position} has no {self._key_field!r}"
            raise ParseError(msg)

        title = non_empty_string(raw_item.get(self._title_field))
        if title is None:
            msg = f"Object {position} ({key!r}) has no {self._title_field!r}"
            raise ParseError(msg)

        url = non_empty_string(raw_item.get(self._url_field)) if self._url_field else None
        price = _price(raw_item.get(self._price_field)) if self._price_field else None
        text = (non_empty_string(raw_item.get(self._text_field)) or "") if self._text_field else ""
        return Item(key=key, title=title, url=url, price=price, text=text)


def _price(raw_price: _JsonValue) -> float | None:
    """Return the value of a price field as a float, if it holds a price.

    Args:
        raw_price: Field value from the API.

    Returns:
        A number as a float, or a string parsed for a price, or None.
    """
    if raw_price is None or isinstance(raw_price, bool):
        return None
    if isinstance(raw_price, int | float):
        return float(raw_price)
    return parse_price(str(raw_price))
