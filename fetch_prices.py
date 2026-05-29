#!/usr/bin/env python3
"""Pull current price + 24h change for each coin in watchlist.yml.

Prices are a solved problem: they come from the CoinGecko API, not the
scraper. The scraper's job is the news, where there is no clean API.
This script is plain deterministic code. No LLM runs here.
"""
import os
import json
import pathlib
import datetime
import urllib.parse
import urllib.request

import yaml  # pip install pyyaml

ROOT = pathlib.Path(__file__).resolve().parent
WATCHLIST = ROOT / "watchlist.yml"
OUT = ROOT / "data" / "prices.json"

API = "https://api.coingecko.com/api/v3/simple/price"
# Optional. Set COINGECKO_API_KEY to use the free Demo plan (higher rate
# limit). The keyless public endpoint works fine for a few calls a day.
DEMO_KEY = os.environ.get("COINGECKO_API_KEY")


def main() -> None:
    coins = yaml.safe_load(WATCHLIST.read_text())["coins"]

    params = {
        "ids": ",".join(coins),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    if DEMO_KEY:
        params["x_cg_demo_api_key"] = DEMO_KEY

    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)

    rows = []
    for cid in coins:
        d = data.get(cid, {})
        rows.append({
            "id": cid,
            "usd": d.get("usd"),
            "change_24h": d.get("usd_24h_change"),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "prices": rows,
    }, indent=2))
    print(f"Wrote {len(rows)} prices to {OUT}")


if __name__ == "__main__":
    main()
