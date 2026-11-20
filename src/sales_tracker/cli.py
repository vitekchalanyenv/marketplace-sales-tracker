"""Command line: `uv run python -m sales_tracker sync gumroad [--since YYYY-MM-DD]`."""

import argparse
import os
import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

from sales_tracker import db, gumroad

DB_PATH = Path("data/private/sales.db")
REFUND_WINDOW_DAYS = 30


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("datum musí být ve tvaru YYYY-MM-DD") from None


def sync_gumroad(
    token: str,
    db_path: Path,
    since: date | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    today: date | None = None,
) -> int:
    conn = db.connect(db_path)
    try:
        if since is None and db.has_sales(conn, gumroad.MARKETPLACE):
            # Re-read the last 30 days so refunds of already stored sales are picked up.
            today = today or datetime.now(UTC).date()
            since = today - timedelta(days=REFUND_WINDOW_DAYS)

        client = gumroad.GumroadClient(token, transport=transport, sleep=sleep)
        try:
            records = client.fetch_sales(after=since)
        except gumroad.GumroadAuthError:
            print("Token je neplatný nebo nemá oprávnění view_sales. Zkontroluj GUMROAD_ACCESS_TOKEN v .env.")
            return 1
        except gumroad.GumroadError as exc:
            print(f"Stažení z Gumroadu selhalo: {exc} Nic se neuložilo.")
            return 1

        sales, skipped = [], []
        for record in records:
            try:
                sales.append(gumroad.parse_sale(record))
            except gumroad.SkipRecord as skip:
                skipped.append(skip)

        result = db.upsert_sales(conn, sales)
    finally:
        conn.close()

    for skip in skipped:
        print(f"Přeskočeno: prodej {skip.external_id or '(bez ID)'} – {skip.reason}")
    for sale in sales:
        if gumroad.has_affiliate(sale.raw):
            print(
                f"Upozornění: prodej {sale.external_id} má affiliate, "
                "čistý příjem neodečítá jeho provizi."
            )
    od = f"od {since.isoformat()}" if since else "vše"
    print(
        f"Gumroad ({od}): staženo {len(records)}, nových {result.new}, "
        f"aktualizovaných {result.updated}, přeskočeno {len(skipped)}."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sales_tracker")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="stáhne prodeje z marketplace")
    sync.add_argument("marketplace", choices=["gumroad"])
    sync.add_argument("--since", type=_date, help="stáhnout prodeje od data (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    # Explicit path: without it python-dotenv searches upwards from this file, not from cwd.
    load_dotenv(Path.cwd() / ".env")
    token = os.environ.get("GUMROAD_ACCESS_TOKEN", "").strip()
    if not token:
        print("Chybí GUMROAD_ACCESS_TOKEN v .env. Zkopíruj .env.example jako .env a doplň token.")
        return 1

    return sync_gumroad(token, DB_PATH, since=args.since)
