---
title: "A daily crypto-news agent in an afternoon (with Claude skills)"
published: false
tags: claude, scraping, agents, python
---

I wanted a small thing: every morning, pull prices, scrape what the crypto press is saying, write me a short brief on what moved and what's worth watching. The kind of half-built side project that usually dies after the first scraper.

I shipped most of it in an afternoon using three Claude Code skills — `/scrape`, `/web-setup`, and `/schedule`. The pipeline now runs autonomously on Scrapy Cloud + GitHub Actions + a Claude cloud routine. Every morning I open one markdown file on GitHub and read what happened.

![The daily brief on GitHub](./images/briefs-on-github.png)
*The brief, rendered on GitHub each morning — movement, narrative, worth-watching, expandable headlines.*

Here's how, and the parts where I had to rework the design.

## What you'll need

- A Zyte account (free tier) — for Scrapy Cloud
- A GitHub account
- A claude.ai subscription — for the cloud routine
- Claude Code CLI v2.1.80+ locally

## 0. Decide what to watch

Before any code, there's one file you edit. `watchlist.yml` is the single source of truth — coins to track, sites to scrape. Everything downstream reads from it.

```yaml
# watchlist.yml — the only file you edit to make this yours
coins:
  - bitcoin
  - ethereum
  - solana
sources:
  - https://www.coindesk.com/
  - https://www.theblock.co/
  - https://decrypt.co/
```

`coins` are [CoinGecko IDs](https://api.coingecko.com/api/v3/coins/list) — these drive the price pull. `sources` are news sites — each gets its own spider (next step). Editing this file is how you fork the project for your own watch.

## 1. Build the scraper with `/scrape`

`/scrape` is a Claude Code skill from Zyte's [claude-skills repo](https://github.com/zyte-ai/claude-skills). Install it once, and you get the full scraper-build workflow as a single command. Run it once per source in `watchlist.yml`.

I'd normally hand-roll a Playwright script for this and burn a couple of hours iterating on selectors. This took ~20 minutes and I didn't open DevTools once.

Install the plugin in Claude Code, then:

```
/scrape https://www.coindesk.com/ news articles: headline, author, published date, body, url
```

What happens during the run:

1. **Explore** — fetches the homepage + a sample article page, classifies links (item / sub-category / pagination)
2. **Propose a schema** — analyzes the detail page, pulls every field it can find (JSON-LD, microdata, plain HTML), shows them grouped as "requested" (what you asked for) vs "discovered" (extras it found). You approve, drop, rename
3. **Validate across variants** — downloads 2-3 more detail pages + listing pages, compares raw HTML vs Playwright-rendered, picks whichever yields better coverage
4. **Optional browser review** — opens a local HTML page where you can spot-check the extracted values against the live pages side-by-side
5. **Generate code** — writes a Scrapy project with [web-poet](https://web-poet.readthedocs.io/) page objects, item dataclasses, fixtures, and pytest tests
6. **Test** — runs the fixture tests against your sample pages so you know on day one what passes

Mine finished at 20 fields per article (5 I asked for, 15 the agent suggested) with **77/81 fixture tests passing on first run**. The four failures were minor whitespace differences in expected values.

The generated page object leans on CoinDesk's JSON-LD `NewsArticle` block as the primary source, with HTML fallbacks for fields JSON-LD doesn't carry (editor, hero image caption, etc.). I'm not sure how it'll hold up the next time CoinDesk redesigns — but the JSON-LD layer is usually the last thing sites change, so my guess is the spider survives layouts. I'll find out.

Skills repo: **[github.com/zyte-ai/claude-skills](https://github.com/zyte-ai/claude-skills)** — also has `/scrape-spec`, `/scrape-codegen`, `/scrape-scrapy-cloud`, and a few others if you want to peek under the hood or run the steps individually.

## 2. Deploy to Scrapy Cloud

The `/scrape` skill offers to deploy at the end. Say yes. It writes a `scrapinghub.yml`, runs `shub deploy`, gives you a job URL. Schedule the daily crawl in the Scrapy Cloud UI: **Periodic Jobs → Add → pick spider → set cron**.

## 3. A GitHub Action that pulls fresh data

The spider runs daily. To pull its items into your repo every morning before the brief gets written, add a workflow:

```yaml
# .github/workflows/fetch-data.yml
on:
  schedule:
    - cron: "25 3 * * *"  # 5 min before the brief routine
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pyyaml
      - run: python fetch_prices.py
      - env: { SHUB_APIKEY: "${{ secrets.SHUB_APIKEY }}" }
        run: python fetch_news.py
      - run: |
          git config user.name "bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/ && git commit -m "data: $(date -u +%F)" || true
          git push
```

Store `SHUB_APIKEY` as a repo secret. The Action commits `data/prices.json` and `data/news.json` to `main` each morning.

## 4. The Claude routine that writes the brief

Connect GitHub to claude.ai once:

```
/web-setup
```

Then in Claude Code, `/schedule` walks you through creating a daily routine. The prompt I ended up with (after a few iterations) reads roughly like:

> *Read `data/prices.json` and `data/news.json` from the cloned repo. Write a brief with three parts: movement (one line per coin: price + 24h change + arrow), narrative (2-3 sentences synthesizing the news, grouped by theme, sources named), worth watching (up to three things to track). Append the brief to `briefs.md` at the top under the marker — if today's date already exists, replace that section. Update `data/latest.json` for the dashboard. Commit and push.*

Full prompt is in [my repo](https://github.com/NehaSetia-DA/crypto-watch-agent) if you want to lift it. Pin its cron ~30 minutes after the Action's so fresh data is already on `main` when the routine clones.

The routine clones, reads, synthesizes, pushes back. Total agent time per run: ~2 minutes.

Watch your brief grow at `https://github.com/YOU/REPO/blob/main/briefs.md`. GitHub renders the markdown.

## What didn't work (and the workaround)

My first cut tried to keep the **entire** pipeline (prices + news fetch + brief + email) inside the Claude routine. It broke on the cloud sandbox's network policy: `api.coingecko.com`, `app.zyte.com`, and `api.resend.com` all returned `403 host-not-allowed` from the proxy. I tried flipping the env's "Domain allowlist" to "All domains," verifying the egress toggle was on, creating a fresh routine to dodge any cached policy, waiting ~15 minutes for propagation. None of it changed the result.

I'm not sure if this is a bug or intentional sandboxing I couldn't find docs for. Either way, fighting it past an hour wasn't going to pay off.

The fix: **split the work**. GitHub Actions has unrestricted egress, so I moved the fetching there. The routine now only reads files from the cloned repo and commits — no external API calls at all. The agent still does the only thing only an agent can do: the synthesis. Cleaner separation than I'd planned, actually.

Same story for email — I tried Resend from inside the routine, got blocked, gave up on email for now. If you want it, send from the Action step (full network).

## How to expand

- **More sources**: add the URL to `watchlist.yml`, run `/scrape <url>` for it, deploy. Each source gets its own spider + its own daily Scrapy Cloud job. The routine reads them all and synthesizes across.
- **More coins**: add the CoinGecko ID to `coins:` in `watchlist.yml`. The price pull picks it up automatically — no other change needed.
- **Custom voice**: the routine reads a `daily_brief.md` prompt file from your repo. Edit it to change tone, depth, what to surface
- **Email/Slack**: add a notification step at the end of the Action (the routine can't, the Action can)
- **Public dashboard**: the repo ships with a `dashboard.html` that reads `data/latest.json` and shows cards. Enable GitHub Pages and bookmark `you.github.io/repo/dashboard.html`:

  ![crypto-watch dashboard](./images/dashboard.png)
- **Backfill**: the spider keeps job history. Loop over old jobs to backfill `briefs.md` for any date

Tomorrow morning, GitHub will show me what moved without my laptop being on. I'll check back in a month to see if anything broke.

Repo: [github.com/NehaSetia-DA/crypto-watch-agent](https://github.com/NehaSetia-DA/crypto-watch-agent)
