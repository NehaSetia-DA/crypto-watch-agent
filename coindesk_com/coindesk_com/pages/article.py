"""Page object for CoinDesk article pages.

Extraction strategy:
- Most structured fields come from the page's JSON-LD ``NewsArticle`` blob
  (``<script id="schema" type="application/ld+json">``).
- Body, what_to_know, tags, editor_name, read_time, hero_image_caption,
  author_url and article_body_html are scraped from the rendered HTML
  because they are either absent from JSON-LD or only available with the
  formatting / relative-URL form CoinDesk uses on-page.
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from urllib.parse import urlparse

from lxml import etree, html as lxml_html
from parsel import Selector
from web_poet import Returns, WebPage, field, handle_urls

from coindesk_com.items import Article


# Classes on inline blocks inside the article body that must be skipped
# (ad placeholders, video embeds, sponsored markers, etc).
_BODY_SKIP_CLASSES = (
    "article-ad",
    "ad-desktop",
    "ad-mobile",
    "article-video",
    "premium-sponsored-hide",
    "premium-hide",
)


def _has_skip_class(el) -> bool:
    cls = el.get("class") or ""
    return any(skip in cls for skip in _BODY_SKIP_CLASSES)


def _portable_text_to_string(value) -> str | None:
    """Flatten a Sanity portable-text ``description`` field to a plain string.

    The value can be a plain string (some authors) or a list of block dicts
    with ``children[*].text`` spans (the common case). Whitespace inside
    spans is preserved verbatim because the expected bios on CoinDesk
    include intentional inner double-spaces.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, list):
        return None

    blocks: list[str] = []
    for block in value:
        if not isinstance(block, dict):
            continue
        children = block.get("children") or []
        spans = [c.get("text", "") for c in children if isinstance(c, dict)]
        if spans:
            blocks.append("".join(spans))
    text = "\n".join(blocks).strip()
    return text or None


@handle_urls("coindesk.com")
class ArticlePage(WebPage, Returns[Article]):
    # ---------- shared helpers ----------

    @cached_property
    def _sel(self) -> Selector:
        """Selector built directly from the HTML body.

        Used by :pyattr:`_jsonld` because the regular ``self.css`` accessor
        from :class:`web_poet.WebPage` resolves ``self.url`` to compute a
        base URL — but ``self.url`` is itself an ``@field`` on this class
        that reads from ``_jsonld``, which would recurse.
        """
        return Selector(text=self.html)

    @cached_property
    def _jsonld(self) -> dict:
        """Parse the NewsArticle JSON-LD payload from ``script#schema``."""
        raw = self._sel.css("script#schema::text").get()
        if not raw:
            # Fall back to scanning every ld+json script for a NewsArticle.
            for blob in self._sel.css('script[type="application/ld+json"]::text').getall():
                try:
                    parsed = json.loads(blob)
                except (TypeError, ValueError):
                    continue
                candidates = parsed if isinstance(parsed, list) else [parsed]
                for entry in candidates:
                    if isinstance(entry, dict) and entry.get("@type") in (
                        "NewsArticle",
                        "Article",
                    ):
                        return entry
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    return entry
            return {}
        return data if isinstance(data, dict) else {}

    @cached_property
    def _primary_author(self) -> dict:
        """First entry of the JSON-LD ``author`` field (an array on CoinDesk)."""
        author = self._jsonld.get("author")
        if isinstance(author, list) and author:
            first = author[0]
            return first if isinstance(first, dict) else {}
        if isinstance(author, dict):
            return author
        return {}

    @cached_property
    def _document_body(self):
        """The ``<div class="document-body">`` element inside ``article-body``.

        Returns the underlying lxml element or ``None`` if the article body
        module is absent.
        """
        nodes = self.css(
            'div[data-module-name="article-body"] div.document-body'
        )
        if not nodes:
            return None
        return nodes[0].root

    @cached_property
    def _body_blocks(self) -> list:
        """Direct child block elements of ``.document-body`` that carry prose.

        Skips ad/video/sponsored wrappers; keeps ``<p>``, ``<ul>``, ``<ol>``,
        and similar text-bearing blocks.
        """
        root = self._document_body
        if root is None:
            return []
        return [child for child in root if not _has_skip_class(child)]

    # ---------- @field methods ----------

    @field
    def headline(self) -> str | None:
        value = self._jsonld.get("headline")
        if isinstance(value, str) and value.strip():
            return value
        return self.css(
            'div[data-module-name="article-header"] h1::text'
        ).get()

    @field
    def author(self) -> str | None:
        name = self._primary_author.get("name")
        if isinstance(name, str) and name.strip():
            return name
        return self.css(
            'div[data-module-name="article-header"] a[href^="/author/"]::text'
        ).get()

    @field
    def date_published(self) -> str | None:
        value = self._jsonld.get("datePublished")
        return value if isinstance(value, str) and value else None

    @field
    def body(self) -> str | None:
        blocks = self._body_blocks
        if not blocks:
            return None

        paragraphs: list[str] = []
        has_list_items = False
        for block in blocks:
            tag = block.tag
            if tag in ("ul", "ol"):
                for li in block.iter("li"):
                    text = " ".join(li.text_content().split())
                    if text:
                        paragraphs.append(text)
                        has_list_items = True
            elif tag == "p":
                text = " ".join(block.text_content().split())
                if text:
                    paragraphs.append(text)
            else:
                # Headings, blockquotes, etc — keep their text content.
                text = " ".join(block.text_content().split())
                if text:
                    paragraphs.append(text)

        if not paragraphs:
            return None
        separator = "\n" if has_list_items else "\n\n"
        return separator.join(paragraphs)

    @field
    def url(self) -> str | None:
        value = self._jsonld.get("url")
        if isinstance(value, str) and value:
            return value
        # Use ``self._sel`` instead of ``self.css`` because ``self.css`` would
        # resolve ``self.url`` (this very field) to build a base URL — infinite
        # recursion. ``_sel`` is built directly from ``self.html``.
        canonical = self._sel.css('link[rel="canonical"]::attr(href)').get()
        if canonical:
            return canonical
        return str(self.response.url)

    @field
    def subheadline(self) -> str | None:
        value = self._jsonld.get("abstract")
        if isinstance(value, str) and value.strip():
            return value
        return self.css(
            'div[data-module-name="article-header"] h2::text'
        ).get()

    @field
    def section(self) -> str | None:
        value = self._jsonld.get("articleSection")
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and first.strip():
                return first
        return self.css(
            "div.article-content-wrapper.row-start-1 a::text"
        ).get()

    @field
    def author_url(self) -> str | None:
        # Prefer the on-page byline anchor — it is already relative.
        href = self.css(
            'div[data-module-name="article-header"] a[href^="/author/"]::attr(href)'
        ).get()
        if href:
            return href
        # Fallback: derive a relative path from the JSON-LD absolute URL.
        absolute = self._primary_author.get("url")
        if isinstance(absolute, str) and absolute:
            path = urlparse(absolute).path
            return path or None
        return None

    @field
    def author_job_title(self) -> str | None:
        value = self._primary_author.get("jobTitle")
        if isinstance(value, str) and value.strip():
            return value
        return None

    @field
    def author_bio(self) -> str | None:
        return _portable_text_to_string(self._primary_author.get("description"))

    @field
    def editor_name(self) -> str | None:
        # The byline reads "By <author> | Edited by <editor>". The editor is
        # the second `/author/` anchor inside the header module. Anchor on
        # the literal "Edited by" text for resilience.
        editor = self.xpath(
            '//div[@data-module-name="article-header"]'
            '//span[contains(normalize-space(.), "Edited by")]'
            '/following::a[starts-with(@href, "/author/")][1]/text()'
        ).get()
        if editor:
            return editor.strip() or ""
        # Fallback: second /author/ anchor in the header byline.
        anchors = self.css(
            'div[data-module-name="article-header"] a[href^="/author/"]::text'
        ).getall()
        if len(anchors) >= 2:
            return anchors[1].strip() or ""
        return ""

    @field
    def date_modified(self) -> str | None:
        value = self._jsonld.get("dateModified")
        # CoinDesk emits an empty string when the article has not been
        # modified; mirror that rather than returning None so the spec
        # example (`""`) is reproduced exactly.
        if isinstance(value, str):
            return value
        return ""

    @field
    def read_time(self) -> str | None:
        span = self.xpath(
            '//div[@data-module-name="article-header"]'
            '//span[contains(normalize-space(.), "min read")]'
        )
        if not span:
            return None
        text = span[0].xpath("string(.)").get() or ""
        text = " ".join(text.split())
        return text or None

    @field
    def hero_image_url(self) -> str | None:
        image = self._jsonld.get("image")
        if isinstance(image, dict):
            url = image.get("url")
            if isinstance(url, str) and url:
                return url
        if isinstance(image, list) and image:
            first = image[0]
            if isinstance(first, dict):
                url = first.get("url")
                if isinstance(url, str) and url:
                    return url
            elif isinstance(first, str) and first:
                return first
        thumbnail = self._jsonld.get("thumbnailUrl")
        if isinstance(thumbnail, str) and thumbnail:
            return thumbnail
        return None

    @field
    def hero_image_caption(self) -> str | None:
        # The hero figure sits in the article-header column above the body.
        caption = self.css(
            "div.article-content-wrapper.row-start-3 figure figcaption::text"
        ).get()
        if caption is not None:
            return caption.strip()
        # Fallback: the first figcaption anywhere in the article frame.
        caption = self.css("figure figcaption::text").get()
        if caption is not None:
            return caption.strip()
        return ""

    @field
    def what_to_know(self) -> list[str] | None:
        items = self.xpath(
            '//h4[contains(normalize-space(.), "What to know")]'
            '/following-sibling::div//ul/li'
        ).getall()
        if not items:
            return []
        result: list[str] = []
        for raw in items:
            try:
                el = lxml_html.fragment_fromstring(raw)
            except (etree.ParserError, etree.XMLSyntaxError):
                continue
            text = " ".join(el.text_content().split())
            if text:
                result.append(text)
        return result

    @field
    def article_body_html(self) -> str | None:
        root = self._document_body
        if root is None:
            return None

        fragments: list[str] = []
        children = [c for c in root if not _has_skip_class(c)]
        for idx, child in enumerate(children):
            serialized = lxml_html.tostring(
                child, method="html", encoding="unicode", with_tail=False
            )
            # CoinDesk sometimes appends a trailing "UPDATE" paragraph wrapped
            # only in <em>/<strong>; the canonical HTML drops the outer <p>
            # in that case. Detect: last block, a <p>, whose inner HTML opens
            # with <em> and contains "UPDATE".
            if (
                idx == len(children) - 1
                and child.tag == "p"
                and len(child) >= 1
                and child[0].tag == "em"
                and "UPDATE" in (child.text_content() or "")
            ):
                inner = "".join(
                    lxml_html.tostring(c, method="html", encoding="unicode")
                    for c in child
                )
                serialized = inner
            fragments.append(serialized)

        if not fragments:
            return None
        return "".join(fragments)

    @field
    def tags(self) -> list[str] | None:
        values = self.css(
            'div[data-module-name="article-tags"] a[href^="/tag/"]::text'
        ).getall()
        cleaned = [v.strip() for v in values if v and v.strip()]
        return cleaned or []

    @field
    def keywords(self) -> list[str] | None:
        value = self._jsonld.get("keywords")
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        if isinstance(value, str) and value:
            # Some sites emit a comma-separated string.
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    @field
    def article_id(self) -> str | None:
        value = self._jsonld.get("identifier")
        if isinstance(value, str) and value:
            return value
        return self.css('meta[name="content_id"]::attr(content)').get()
