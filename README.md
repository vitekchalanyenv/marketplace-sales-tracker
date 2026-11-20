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
```

Built with AI coding agents (Claude Code). Mistakes the AI made and how they were caught are logged in
[`docs/AI_CHYBY.md`](docs/AI_CHYBY.md).
