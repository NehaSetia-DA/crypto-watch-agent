"""Page object for CoinDesk navigation/listing pages.

Covers three layouts under coindesk.com:

* The home page (``/``) — many heterogeneous modules
  (``data-module-name='latest-crypto-news'``, ``press-release``, ``opinion``,
  ``policy``, the 5 section blocks ``finance``/``markets``/``tech``/``opinion``/
  ``policy``).
* Section landing pages (e.g. ``/markets``, ``/policy``) — a main feed of
  ``a.content-card-title`` cards plus two cross-section teaser blocks
  (``div.content-card-image--story-card``) introduced by
  ``a.font-title.text-subtle.uppercase.flex`` section-header anchors.

Extraction is done with parsel selectors over ``self.html``. We deliberately
build a fresh ``Selector(text=self.html)`` inside each ``cached_property``
that needs to read the HTML — going through ``self.url`` / ``self.css``
during selector construction would re-enter the page object's own ``url``
``@field`` and cause infinite recursion.
"""

from __future__ import annotations

from functools import cached_property
from urllib.parse import urljoin

from parsel import Selector
from web_poet import Returns, WebPage, field, handle_urls

from coindesk_com.items import Navigation, NavigationLink


_BASE_URL = "https://www.coindesk.com"

# Section modules that appear on the front page, in display order.
_FRONT_SECTION_KEYS = ("finance", "markets", "tech", "opinion", "policy")


def _clean(text: str | None) -> str:
    """Collapse whitespace and trim, returning an empty string for ``None``."""
    if text is None:
        return ""
    return " ".join(text.split()).strip()


def _abs_url(href: str | None) -> str | None:
    """Resolve a (possibly relative) href against the CoinDesk base URL."""
    if not href:
        return None
    href = href.strip()
    if not href:
        return None
    return urljoin(_BASE_URL + "/", href)


@handle_urls("coindesk.com")
class NavigationPage(WebPage, Returns[Navigation]):
    """Extract navigation links from CoinDesk listing pages."""

    @cached_property
    def _sel(self) -> Selector:
        """Parsel selector built directly from ``self.html``.

        Using ``Selector(text=self.html)`` instead of ``self.css`` avoids any
        path through ``self.url`` while a ``url`` ``@field`` is being resolved.
        """
        return Selector(text=self.html)

    # ------------------------------------------------------------------ items

    def _items_from_latest_crypto_news(self) -> list[NavigationLink]:
        """Front-page ``latest-crypto-news`` module.

        Each card is an ``<a target='_self' href='/section/YYYY/MM/DD/slug'>``
        containing a serif title ``<div>`` and a subtle description ``<span>``.
        Text is ``"{title}\\n{description}"``; the trailing newline+description
        is omitted when the description is missing.
        """
        out: list[NavigationLink] = []
        # The outer module wrapper and inner cards both carry the same
        # ``data-module-name`` attribute. We restrict to anchors that have a
        # serif title ``<div>`` child to dedupe.
        anchors = self._sel.xpath(
            "//div[@data-module-name='latest-crypto-news']"
            "//a[@target='_self' and .//div[contains(@class,'font-serif')]]"
        )
        for a in anchors:
            href = a.attrib.get("href")
            if not href:
                continue
            title = _clean(
                "".join(a.xpath(".//div[contains(@class,'font-serif')]//text()").getall())
            )
            description = _clean(
                "".join(a.xpath(".//span[contains(@class,'font-sans')]//text()").getall())
            )
            if not title and not description:
                continue
            text = f"{title}\n{description}" if description else title
            out.append(NavigationLink(url=_abs_url(href), text=text))
        return out

    def _items_from_press_release(self) -> list[NavigationLink]:
        """Front-page ``press-release`` carousel — title-only cards."""
        out: list[NavigationLink] = []
        anchors = self._sel.css(
            "div[data-module-name='press-release'] a.content-card-title"
        )
        for a in anchors:
            href = a.attrib.get("href")
            if not href:
                continue
            title = _clean(" ".join(a.css("h2 *::text, h2::text").getall()))
            out.append(NavigationLink(url=_abs_url(href), text=title))
        return out

    def _items_from_opinion(self) -> list[NavigationLink]:
        """Front-page ``opinion`` module — title anchors with an ``<h3>`` child."""
        out: list[NavigationLink] = []
        anchors = self._sel.xpath(
            "//div[@data-module-name='opinion']"
            "//a[starts-with(@href, '/opinion/') and ./h3]"
        )
        for a in anchors:
            href = a.attrib.get("href")
            if not href:
                continue
            title = _clean(" ".join(a.xpath(".//h3//text()").getall()))
            out.append(NavigationLink(url=_abs_url(href), text=title))
        return out

    def _items_from_policy_subitems(self) -> list[NavigationLink]:
        """Front-page ``policy`` module — small sub-items (skip the hero card)."""
        out: list[NavigationLink] = []
        anchors = self._sel.xpath(
            "//div[@data-module-name='policy']"
            "//a[contains(@class,'border-b') and ./h3]"
        )
        for a in anchors:
            href = a.attrib.get("href")
            if not href:
                continue
            title = _clean(" ".join(a.xpath(".//h3//text()").getall()))
            out.append(NavigationLink(url=_abs_url(href), text=title))
        return out

    def _items_from_content_cards(self) -> list[NavigationLink]:
        """Section landing pages — primary ``a.content-card-title`` cards.

        Each anchor wraps a single ``<h2>`` with the headline text.
        """
        out: list[NavigationLink] = []
        anchors = self._sel.css("a.content-card-title")
        for a in anchors:
            href = a.attrib.get("href")
            if not href:
                continue
            title = _clean(" ".join(a.css("h2 *::text, h2::text").getall()))
            out.append(NavigationLink(url=_abs_url(href), text=title))
        return out

    def _items_from_story_cards(self) -> list[NavigationLink]:
        """Section pages — cross-section teaser cards (URL-only, empty text).

        Each ``div.content-card-image--story-card`` container holds two anchors
        with the same ``href`` (image wrapper + headline wrapper). We use the
        headline anchor and emit an empty ``text`` per the section-page
        convention for these sidebar teasers.
        """
        out: list[NavigationLink] = []
        anchors = self._sel.css(
            "div.content-card-image--story-card a.hover\\:underline.text-default"
        )
        seen: set[str] = set()
        for a in anchors:
            href = a.attrib.get("href")
            if not href or href in seen:
                continue
            seen.add(href)
            out.append(NavigationLink(url=_abs_url(href), text=""))
        return out

    @field
    def items(self) -> list[NavigationLink] | None:
        collected: list[NavigationLink] = []
        seen: set[str] = set()

        def _extend(links: list[NavigationLink]) -> None:
            for link in links:
                key = link.url or ""
                if not key or key in seen:
                    continue
                seen.add(key)
                collected.append(link)

        # Front-page modules (no-op on section pages where these selectors
        # match nothing).
        _extend(self._items_from_latest_crypto_news())
        _extend(self._items_from_press_release())
        _extend(self._items_from_opinion())
        _extend(self._items_from_policy_subitems())

        # Section-page patterns (no-op on the front page where these
        # selectors match nothing).
        _extend(self._items_from_content_cards())
        _extend(self._items_from_story_cards())

        return collected or None

    # -------------------------------------------------------------- next_page

    @field
    def next_page(self) -> str | None:
        """CoinDesk listing pages are not paginated. Probe defensively."""
        href = self._sel.css("link[rel='next']::attr(href)").get()
        if href:
            return _abs_url(href)
        href = self._sel.css("a[rel='next']::attr(href)").get()
        if href:
            return _abs_url(href)
        return None

    # ----------------------------------------------------------- subcategories

    def _subcategories_from_front(self) -> list[NavigationLink]:
        """Front-page subcategories: one header anchor per section module.

        We iterate the well-known module keys (``finance``, ``markets``,
        ``tech``, ``opinion``, ``policy``) in display order and pick each
        module's first ``<a>`` containing an ``<h2>``. This preserves the
        ``finance``-module → ``/business`` ("Finance") mapping naturally
        because we read href and text from the DOM rather than derive them
        from the module key.
        """
        out: list[NavigationLink] = []
        for key in _FRONT_SECTION_KEYS:
            anchors = self._sel.xpath(
                f"//div[@data-module-name='{key}']//a[./h2]"
            )
            if not anchors:
                continue
            a = anchors[0]
            href = a.attrib.get("href")
            text = _clean(" ".join(a.xpath(".//h2//text()").getall()))
            if not href or not text:
                continue
            out.append(NavigationLink(url=_abs_url(href), text=text))
        return out

    def _subcategories_from_section_headers(self) -> list[NavigationLink]:
        """Section landing pages: ``a.font-title.text-subtle.uppercase.flex``."""
        out: list[NavigationLink] = []
        anchors = self._sel.css("a.font-title.text-subtle.uppercase.flex")
        for a in anchors:
            href = a.attrib.get("href")
            text = _clean(" ".join(a.css("*::text, ::text").getall()))
            if not href or not text:
                continue
            out.append(NavigationLink(url=_abs_url(href), text=text))
        return out

    @field
    def subcategories(self) -> list[NavigationLink] | None:
        # Front-page section modules take precedence when present.
        front = self._subcategories_from_front()
        if front:
            return front
        section = self._subcategories_from_section_headers()
        return section or None
