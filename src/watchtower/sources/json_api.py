"""JSONAPISource for monitoring a list of objects returned by a JSON API."""

from __future__ import annotations

from collections.abc import Iterable

import httpx

from watchtower.models import Item
from watchtower.registry import register_source
from watchtower.sources.http import DEFAULT_TIMEOUT_SECONDS, HttpSource


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
        raise NotImplementedError

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
        raise NotImplementedError
