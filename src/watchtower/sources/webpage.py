"""WebPageSource for monitoring repeated elements on an HTML page."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from watchtower.errors import ParseError
from watchtower.models import Item
from watchtower.registry import register_source
from watchtower.sources.http import DEFAULT_TIMEOUT_SECONDS, HttpSource
from watchtower.sources.parsing import parse_price


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
        self._selector = selector
        self._title_selector = title_selector
        self._price_selector = price_selector
        self._key_attribute = key_attribute

    def parse(self, raw: str) -> Iterable[Item]:
        """Parse an HTML page with BeautifulSoup into Items.

        Args:
            raw: HTML returned by `fetch()`.

        Returns:
            An iterable of Items, one per element matching `selector`.

        Raises:
            ParseError: If a matched element has no title.
        """
        soup = BeautifulSoup(raw, "html.parser")
        return [
            self._to_item(element, position)
            for position, element in enumerate(soup.select(self._selector), start=1)
        ]

    def _to_item(self, element: Tag, position: int) -> Item:
        """Convert one matched element to an Item, validating its title."""
        href = self._href(element)
        title = self._title(element)
        if not title:
            msg = f"Element {position} matching {self._selector!r} has no title"
            raise ParseError(msg)
        return Item(
            key=self._key(element, href, title),
            title=title,
            url=urljoin(self.url, href) if href is not None else None,
            price=self._price(element),
            text=element.get_text(" ", strip=True),
        )

    def _title(self, element: Tag) -> str:
        """Return the title found inside the element."""
        if self._title_selector is None:
            return element.get_text(" ", strip=True)
        title = element.select_one(self._title_selector)
        return title.get_text(" ", strip=True) if title is not None else ""

    def _price(self, element: Tag) -> float | None:
        """Return the price found inside the element, if any."""
        if self._price_selector is None:
            return None
        price = element.select_one(self._price_selector)
        return parse_price(price.get_text(" ", strip=True)) if price is not None else None

    def _key(self, element: Tag, href: str | None, title: str) -> str:
        """Return the stable key of the element."""
        if self._key_attribute is not None:
            value = element.get(self._key_attribute)
            if isinstance(value, str) and value.strip():
                return value
        if href is not None:
            return href
        return title

    @staticmethod
    def _href(element: Tag) -> str | None:
        """Return the href of the element's first link, if it has one."""
        link = element.select_one("a[href]")
        if link is None:
            return None
        href = link.get("href")
        return href if isinstance(href, str) and href.strip() else None
