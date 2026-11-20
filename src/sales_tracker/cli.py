"""Command line: `uv run python -m sales_tracker sync gumroad [--since YYYY-MM-DD]`."""

import argparse
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

from sales_tracker import catalog as catalog_mod
from sales_tracker import db, gumroad

DB_PATH = Path("data/private/sales.db")
CATALOG_PATH = Path("data/private/katalog.yaml")
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
    catalog_path: Path = CATALOG_PATH,
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
    _match_after_sync(catalog_path, db_path)
    return 0


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Czech plural: 1 prodej, 2–4 prodeje, 0 / 5+ prodejů."""
    if n == 1:
        return f"1 {one}"
    return f"{n} {few}" if 2 <= n <= 4 else f"{n} {many}"


def _yaml_snippet(listing: db.UnmatchedListing) -> str:
    # json.dumps gives a double-quoted string that is also valid YAML
    lines = [f"      {listing.marketplace}:"]
    if listing.ref is not None:
        lines.append(f"        - ref: {json.dumps(listing.ref, ensure_ascii=False)}")
        if listing.title is not None:
            lines.append(f"          # název: {listing.title}")
    elif listing.title is not None:
        lines.append(f"        - title: {json.dumps(listing.title, ensure_ascii=False)}")
    return "\n".join(lines)


def _load_catalog(catalog_path: Path) -> catalog_mod.Catalog | None:
    """Load the catalog or print why not. Returns None on any problem."""
    try:
        return catalog_mod.load_catalog(catalog_path)
    except FileNotFoundError:
        print(
            f"Katalog {catalog_path} neexistuje. Založ ho podle vzoru data/sample/katalog.yaml "
            "(formát v docs/spec/M2-katalog.md)."
        )
    except catalog_mod.CatalogError as exc:
        print(f"Katalog {catalog_path} má chyby ({len(exc.errors)}):")
        for error in exc.errors:
            print(f"  - {error}")
    return None


def _print_unmatched(catalog: catalog_mod.Catalog, conn) -> None:
    unmatched = db.unmatched_listings(conn, catalog.match)
    if not unmatched:
        return
    print("\nNespárované listingy (doplň do katalogu):")
    for listing in unmatched:
        label = listing.title or listing.ref or "(bez názvu a ID)"
        print(f"\n- {listing.marketplace}: {label} – {_plural(listing.sales, "prodej", "prodeje", "prodejů")}")
        if listing.ref is not None and listing.title is not None:
            print(f"  ref: {listing.ref}")
        suggestion = catalog.suggest(listing.title)
        if suggestion:
            print(f"  možná patří k produktu: {suggestion} ({catalog.name_of(suggestion)})")
        print("  do katalogu pod 'listings:' daného produktu (odsazení sedí):")
        print(_yaml_snippet(listing))


def catalog_check(catalog_path: Path, db_path: Path) -> int:
    catalog = _load_catalog(catalog_path)
    if catalog is None:
        return 1
    count = _plural(len(catalog.products), "produkt", "produkty", "produktů")
    print(f"Katalog je v pořádku ({count}).")
    conn = db.connect(db_path)
    try:
        _print_unmatched(catalog, conn)
    finally:
        conn.close()
    return 0


def catalog_match(catalog_path: Path, db_path: Path) -> int:
    catalog = _load_catalog(catalog_path)
    if catalog is None:
        print("Párování se nespustilo, nic se nezměnilo.")
        return 1
    conn = db.connect(db_path)
    try:
        result = db.assign_products(conn, catalog.match)
        print(f"Párování: spárováno {result.matched}, nespárováno {result.unmatched}.")
        _print_unmatched(catalog, conn)
    finally:
        conn.close()
    return 0


def _match_after_sync(catalog_path: Path, db_path: Path) -> None:
    if not Path(catalog_path).exists():
        print(f"Katalog {catalog_path} neexistuje, prodeje zůstaly nespárované (viz catalog check).")
        return
    try:
        catalog_mod.load_catalog(catalog_path)
    except catalog_mod.CatalogError:
        print("Katalog má chyby, párování přeskočeno. Spusť: uv run python -m sales_tracker catalog check")
        return
    catalog_match(catalog_path, db_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sales_tracker")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="stáhne prodeje z marketplace")
    sync.add_argument("marketplace", choices=["gumroad"])
    sync.add_argument("--since", type=_date, help="stáhnout prodeje od data (YYYY-MM-DD)")
    catalog = commands.add_parser("catalog", help="katalog produktů a párování prodejů")
    catalog.add_argument("action", choices=["check", "match"])
    args = parser.parse_args(argv)

    if args.command == "catalog":
        if args.action == "check":
            return catalog_check(CATALOG_PATH, DB_PATH)
        return catalog_match(CATALOG_PATH, DB_PATH)

    # Explicit path: without it python-dotenv searches upwards from this file, not from cwd.
    load_dotenv(Path.cwd() / ".env")
    token = os.environ.get("GUMROAD_ACCESS_TOKEN", "").strip()
    if not token:
        print("Chybí GUMROAD_ACCESS_TOKEN v .env. Zkopíruj .env.example jako .env a doplň token.")
        return 1

    return sync_gumroad(token, DB_PATH, since=args.since)
