from scrapy_zyte_api.utils import USER_AGENT as ZAPI_USER_AGENT

BOT_NAME = "coindesk_com"

SPIDER_MODULES = ["coindesk_com.spiders"]
NEWSPIDER_MODULE = "coindesk_com.spiders"

ADDONS = {
    "scrapy_poet.Addon": 300,
    "scrapy_zyte_api.Addon": 500,
}

SCRAPY_POET_DISCOVER = [
    "coindesk_com.pages",
]

_ZYTE_API_USER_AGENT = f"scraping-agent-skills {ZAPI_USER_AGENT}"

# Zyte API is configured but transparent mode is off by default.
# Enable per-spider via custom_settings when needed:
#   custom_settings = {"ZYTE_API_TRANSPARENT_MODE": True}
ZYTE_API_TRANSPARENT_MODE = False

ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1
FEED_EXPORT_ENCODING = "utf-8"
