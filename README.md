# marketplace-sales-tracker

A personal multi-channel sales tracker for 3D assets sold on **Gumroad, Fab, CGTrader and Cosmos (Leartes)**.

It pulls sales from every marketplace into one local database, matches the same product across platforms,
notifies about new sales and writes a weekly summary using an AI agent.

> Work in progress. Status: [`docs/PROGRESS.md`](docs/PROGRESS.md) · Plan: [`docs/PLAN.md`](docs/PLAN.md)

## Why it is interesting

Every marketplace exposes data differently:

| Marketplace | Access |
|---|---|
| Gumroad | REST API (personal access token) |
| Fab | no public API, monthly CSV reports |
| CGTrader | OAuth 2.0 API (access on request) |
| Cosmos | web dashboard only |

The same asset has a different name and ID on each platform, prices come in different currencies and with different
fees. The tracker normalizes all of it into one model of a sale.

## Privacy

Real sales data never leaves the local machine. The repository contains only **synthetic sample data**
(`data/sample/`). Secrets live in `.env` (see `.env.example`).

## Run

```powershell
uv sync
uv run pytest

# copy .env.example to .env and fill in GUMROAD_ACCESS_TOKEN, then:
uv run python -m sales_tracker sync gumroad                     # first run: everything, then last 30 days
uv run python -m sales_tracker sync gumroad --since 2026-01-01

# Cosmos: browser agent (Playwright + installed Chrome, dedicated profile, headless)
uv run python -m sales_tracker sync cosmos --login              # once: log in yourself in the opened window
uv run python -m sales_tracker sync cosmos

# Fab: save the daily sales report CSV into data/private/fab/, then
uv run python -m sales_tracker import fab                       # every CSV in data/private/fab/
uv run python -m sales_tracker import fab path/to/report.csv

# product catalog (data/private/katalog.yaml, see data/sample/katalog.yaml)
uv run python -m sales_tracker catalog check   # validate + list unmatched sales with ready-to-paste YAML
uv run python -m sales_tracker catalog match   # re-assign every sale to a product
```

Sales are stored in `data/private/sales.db` (SQLite, git-ignored). Running a sync twice never creates duplicates;
a changed sale (e.g. a refund) is updated in place. Each sale is matched to a catalog product by exact listing ID or
title only; similar names are offered as suggestions, never matched automatically.

Built with AI coding agents (Claude Code). Mistakes the AI made and how they were caught are logged in
[`docs/AI_CHYBY.md`](docs/AI_CHYBY.md).
