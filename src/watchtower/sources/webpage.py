"""WebPageSource for monitoring repeated elements on an HTML page."""

from __future__ import annotations

from collections.abc import Iterable

import httpx

from watchtower.models import Item
from watchtower.registry import register_source
from watchtower.sources.http import DEFAULT_TIMEOUT_SECONDS, HttpSource


@register_source("webpage")
class WebPageSource(HttpSource):
    """Source producing one Item per element matching a CSS selector."""

    def __init__(
        self,
        url: str,
        selector: str,
        *,
        title_selector: str | None = None,
        price_selector: str | None = None,
        key_attribute: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize WebPageSource.

        Args:
            url: Address of the page.
            selector: CSS selector matching one element per Item.
            title_selector: Selector for the title inside each element; when
                None, the element's own text is the title.
            price_selector: Selector for the price inside each element; when
                None, Items have no price.
            key_attribute: Element attribute holding a stable id, such as
                `data-id`; when None, the first link's `href` is the key,
                falling back to the title.
            timeout: Request timeout in seconds.
            transport: Optional transport used by tests.
        """
        super().__init__(url, timeout=timeout, transport=transport)
        self.selector = selector
        self.title_selector = title_selector
        self.price_selector = price_selector
        self.key_attribute = key_attribute

    def parse(self, raw: str) -> Iterable[Item]:
        """Parse an HTML page with BeautifulSoup into Items.

        Args:
            raw: HTML returned by `fetch()`.

        Returns:
            An iterable of Items, one per element matching `selector`.
        """
        raise NotImplementedError
