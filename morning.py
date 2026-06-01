#!/usr/bin/env python3
"""Daily morning refresh — local edition.

Pulls today's prices from CoinGecko and the latest CoinDesk headlines from
your Scrapy Cloud spider, writes them into ``data/latest.json`` in the
shape ``dashboard.html`` expects, and opens the dashboard.

Usage:
    python morning.py

Auth:
    Reads ``SHUB_APIKEY`` from the environment, or from ``~/.scrapinghub.yml``
    (the same file ``shub login`` writes). If neither is set, the script
    still runs but skips the news step — prices alone.

Why this exists:
    The cloud routine path is shelved because Anthropic's sandbox
    silently blocks outbound HTTP despite the env's allowlist being open.
    Until that's fixed, the daily read happens locally: this script
    refreshes data, you open the dashboard.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

LATEST = DATA / "latest.json"

SCRAPY_PROJECT = "864818"
SCRAPY_SPIDER = "coindesk_com"
MAX_HEADLINES = 8


def read_shub_key() -> str | None:
    """Find Scrapy Cloud API key in env or ``~/.scrapinghub.yml``."""
    key = os.environ.get("SHUB_APIKEY")
    if key:
        return key
    yml = pathlib.Path.home() / ".scrapinghub.yml"
    if not yml.exists():
        return None
    for line in yml.read_text().splitlines():
        line = line.strip()
        if line.startswith("default:"):
            return line.split(":", 1)[1].strip()
    return None


def fetch_prices() -> list[dict]:
    """Run ``fetch_prices.py`` and return the prices list."""
    subprocess.run([sys.executable, "fetch_prices.py"], check=True, cwd=ROOT)
    with open(DATA / "prices.json") as f:
        return json.load(f).get("prices", [])


def _shub_get(url: str, api_key: str, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(url)
    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_latest_news(api_key: str) -> list[str]:
    """Top headlines from the most recent finished spider job."""
    try:
        listing = _shub_get(
            f"https://app.zyte.com/api/jobs/list.json?"
            f"project={SCRAPY_PROJECT}&spider={SCRAPY_SPIDER}"
            f"&state=finished&count=1",
            api_key,
        )
    except urllib.error.URLError as e:
        print(f"Could not list Scrapy Cloud jobs: {e}", file=sys.stderr)
        return []

    jobs = listing.get("jobs", []) if isinstance(listing, dict) else []
    if not jobs:
        return []

    job_id = jobs[0]["id"]
    try:
        items = _shub_get(
            f"https://storage.scrapinghub.com/items/{job_id}?format=json",
            api_key,
        )
    except urllib.error.URLError as e:
        print(f"Could not fetch items for {job_id}: {e}", file=sys.stderr)
        return []

    headlines: list[str] = []
    for item in items:
        h = (item or {}).get("headline")
        if h and h not in headlines:
            headlines.append(h)
        if len(headlines) >= MAX_HEADLINES:
            break
    print(f"Pulled {len(headlines)} headlines from job {job_id}")
    return headlines


def main() -> None:
    prices = fetch_prices()

    api_key = read_shub_key()
    if api_key:
        headlines = fetch_latest_news(api_key)
    else:
        headlines = []
        print(
            "(no Scrapy Cloud key — skipping news; "
            "set SHUB_APIKEY or run `shub login`)"
        )

    latest = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "prices": prices,
        "narrative": (
            "Prices and headlines below. The narrative-writing agent is "
            "offline today; read the headlines directly to form your own take."
        ),
        "worth_watching": [],
        "news": (
            [{"source": "coindesk.com", "headlines": headlines}]
            if headlines
            else []
        ),
    }

    LATEST.write_text(json.dumps(latest, indent=2))
    print(f"Wrote {LATEST}")

    # Open the dashboard in the default browser.
    subprocess.run(["open", "dashboard.html"], cwd=ROOT)


if __name__ == "__main__":
    main()
