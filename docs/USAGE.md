# Usage

Everything runs locally from the repository root. Internal docs (specs, progress) are in Czech; this page is not.

## Without accounts: the demo

```powershell
uv sync
uv run pytest
uv run python -m sales_tracker demo               # whole pipeline on made-up data, no accounts or network
uv run python -m sales_tracker demo --dashboard   # ...and the dashboard on the same data
```

## With real data

```powershell
uv run python -m sales_tracker dashboard              # dashboard in the browser (local only), Ctrl+C to stop

# copy .env.example to .env and fill in GUMROAD_ACCESS_TOKEN, then:
uv run python -m sales_tracker sync gumroad                     # first run: everything, then last 30 days
uv run python -m sales_tracker sync gumroad --since 2026-01-01

# Cosmos: browser agent (Playwright + installed Chrome, dedicated profile, headless)
uv run python -m sales_tracker sync cosmos --login              # once: log in yourself in the opened window
uv run python -m sales_tracker sync cosmos
uv run python -m sales_tracker import cosmos                    # fallback: pasted sales table, data/private/cosmos/*.txt

# Fab: save the daily sales report CSV into data/private/fab/, then
uv run python -m sales_tracker import fab                       # every CSV in data/private/fab/
uv run python -m sales_tracker import fab path/to/report.csv

# CGTrader: My Sales → View details → Generate report, save the e-mailed CSV into data/private/cgtrader/, then
uv run python -m sales_tracker import cgtrader                  # every CSV in data/private/cgtrader/

# daily agent: all sources, log in data/private/logs/, morning report e-mail via Resend
# (.env: RESEND_API_KEY, REPORT_EMAIL_TO; ANTHROPIC_API_KEY for the Monday weekly commentary)
uv run python -m sales_tracker run daily
uv run python -m sales_tracker run daily --dry-run                # print the report, send nothing
uv run python -m sales_tracker run daily --dry-run --with-claude  # ...and ask Claude for the weekly commentary
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1   # Task Scheduler, daily 08:00, catches up after boot
powershell -ExecutionPolicy Bypass -File scripts\uninstall_task.ps1

# leave a sale out of all totals (e.g. your own test purchase); --undo counts it again
uv run python -m sales_tracker exclude gumroad <sale id> --reason "test purchase"

# product catalog (data/private/katalog.yaml, see data/sample/katalog.yaml)
uv run python -m sales_tracker catalog check   # validate + list unmatched sales with ready-to-paste YAML
uv run python -m sales_tracker catalog match   # re-assign every sale to a product

# regenerate the README screenshots from the demo
uv run python scripts/demo_screenshot.py
uv run python scripts/dashboard_screenshot.py
```

Secrets go to `.env` only (see [`.env.example`](../.env.example)). Real data stays in git-ignored `data/private/`.
