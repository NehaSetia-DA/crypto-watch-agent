#!/usr/bin/env python3
"""Pull the most recent finished Scrapy Cloud job's items into ``data/news.json``.

Plain deterministic code — no LLM, no scraping logic (the spider already did
that). This just reaches into Scrapy Cloud's storage API and grabs the items.

Auth: ``SHUB_APIKEY`` from the environment. In CI, set it as a repo secret
and pass via ``env:``. Locally, ``shub login`` writes it to
``~/.scrapinghub.yml`` — read it from there as a fallback.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "data" / "news.json"

PROJECT = "864818"
SPIDER = "coindesk_com"
MAX_HEADLINES = 12


def read_api_key() -> str | None:
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


def shub_get(url: str, api_key: str, timeout: int = 30):
    req = urllib.request.Request(url)
    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    api_key = read_api_key()
    if not api_key:
        OUT.write_text(
            json.dumps(
                {
                    "items": [],
                    "error": "SHUB_APIKEY not set",
                    "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "count": 0,
                },
                indent=2,
            )
        )
        print("No SHUB_APIKEY — wrote empty news.json")
        sys.exit(0)

    # 1. Find the most recent finished job
    try:
        listing = shub_get(
            f"https://app.zyte.com/api/jobs/list.json?"
            f"project={PROJECT}&spider={SPIDER}&state=finished&count=1",
            api_key,
        )
    except urllib.error.URLError as e:
        OUT.write_text(
            json.dumps(
                {
                    "items": [],
                    "error": f"job list failed: {e}",
                    "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "count": 0,
                },
                indent=2,
            )
        )
        print(f"Job list failed: {e}", file=sys.stderr)
        sys.exit(0)

    jobs = listing.get("jobs", []) if isinstance(listing, dict) else []
    if not jobs:
        OUT.write_text(
            json.dumps(
                {
                    "items": [],
                    "error": "no finished jobs",
                    "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "count": 0,
                },
                indent=2,
            )
        )
        print("No finished jobs found")
        sys.exit(0)

    job_id = jobs[0]["id"]

    # 2. Pull items
    try:
        items = shub_get(
            f"https://storage.scrapinghub.com/items/{job_id}?format=json",
            api_key,
            timeout=60,
        )
    except urllib.error.URLError as e:
        OUT.write_text(
            json.dumps(
                {
                    "items": [],
                    "error": f"items fetch failed: {e}",
                    "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "count": 0,
                    "job": job_id,
                },
                indent=2,
            )
        )
        print(f"Items fetch failed: {e}", file=sys.stderr)
        sys.exit(0)

    # 3. Slim each item down to what the brief actually needs
    slim = []
    for it in items:
        slim.append(
            {
                "headline": it.get("headline"),
                "subheadline": it.get("subheadline"),
                "section": it.get("section"),
                "url": it.get("url"),
                "date_published": it.get("date_published"),
                "author": it.get("author"),
                "tags": it.get("tags") or [],
            }
        )

    OUT.write_text(
        json.dumps(
            {
                "job": job_id,
                "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
                "count": len(slim),
                "items": slim,
            },
            indent=2,
        )
    )
    print(f"Wrote {len(slim)} items from job {job_id} to {OUT}")


if __name__ == "__main__":
    main()
