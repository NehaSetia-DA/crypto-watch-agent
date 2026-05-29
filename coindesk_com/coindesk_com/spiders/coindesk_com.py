"""Spider for coindesk.com — discovers articles via the homepage and section
listings, then extracts each article using ``ArticlePage``."""

from __future__ import annotations

import scrapy
from scrapy_poet import DummyResponse

from coindesk_com.pages.article import ArticlePage
from coindesk_com.pages.navigation import NavigationPage


class CoindeskComSpider(scrapy.Spider):
    name = "coindesk_com"
    start_urls = ["https://www.coindesk.com"]

    custom_settings = {
        # CoinDesk's article HTML is server-rendered, so raw HTTP responses
        # contain everything we need — no browser rendering required.
        # The project ships with scrapy-zyte-api enabled for cloud crawls,
        # but for local runs without ZYTE_API_KEY we disable the addon.
        "ADDONS": {
            "scrapy_poet.Addon": 300,
        },
        "ZYTE_API_TRANSPARENT_MODE": False,
        # CoinDesk rejects scrapy's default User-Agent with 403.
        "USER_AGENT": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    async def parse(self, response: DummyResponse, nav: NavigationPage):
        """Parse the homepage and section list pages.

        ``NavigationPage`` yields three lists:

        - ``items`` — article URLs to follow (handed off to ``parse_article``)
        - ``subcategories`` — section pages (recurse back into ``parse``)
        - ``next_page`` — pagination cursor (recurse back into ``parse``)
        """
        nav_item = await nav.to_item()

        for link in nav_item.items or []:
            if link.url:
                yield scrapy.Request(link.url, callback=self.parse_article)

        if nav_item.next_page:
            yield scrapy.Request(nav_item.next_page, callback=self.parse)

        for link in nav_item.subcategories or []:
            if link.url:
                yield scrapy.Request(link.url, callback=self.parse)

    async def parse_article(self, response: DummyResponse, page: ArticlePage):
        """Extract a single article using ``ArticlePage``."""
        yield await page.to_item()
