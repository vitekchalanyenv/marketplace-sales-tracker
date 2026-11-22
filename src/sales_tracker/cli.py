"""Command line: sync gumroad|cosmos, import fab|cgtrader, catalog check|match, run daily (see README)."""

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
from sales_tracker import cgtrader, cosmos, daily, db, emailer, fab, fx, gumroad

DB_PATH = Path("data/private/sales.db")
CATALOG_PATH = Path("data/private/katalog.yaml")
FAB_DIR = Path("data/private/fab")
CGTRADER_DIR = Path("data/private/cgtrader")
COSMOS_DIR = Path("data/private/cosmos")
STATE_PATH = Path("data/private/agent_state.json")
LOG_DIR = Path("data/private/logs")
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


def report_paths(path: Path | None, folder: Path, pattern: str = "*.csv") -> list[Path]:
    """The given file, or every matching file in the folder (alphabetical: older periods first)."""
    if path is not None:
        return [path]
    return sorted(folder.glob(pattern)) if folder.is_dir() else []


def _import_reports(
    paths: list[Path],
    db_path: Path,
    *,
    label: str,
    parse,
    format_error: type[Exception],
    catalog_path: Path,
) -> int:
    """Import report files one by one; a broken file is reported and the others still import."""
    code = 0
    imported = False
    conn = db.connect(db_path)
    try:
        for path in paths:
            try:
                report = parse(path)
            except FileNotFoundError:
                print(f"Soubor {path} neexistuje.")
                code = 1
                continue
            except format_error as exc:
                print(f"{path.name}: {exc}. Nic se z něj neuložilo.")
                code = 1
                continue

            for skipped in report.skipped:
                print(f"Přeskočeno: {path.name}, řádek {skipped.line} – {skipped.reason}")
            for warning in getattr(report, "warnings", []):
                print(f"Upozornění: {path.name}, {warning}")
            result = db.upsert_sales(conn, report.sales)
            imported = True
            print(
                f"{label} ({path.name}): řádků {report.rows}, nových {result.new}, "
                f"aktualizovaných {result.updated}, přeskočeno {len(report.skipped)}."
            )
    finally:
        conn.close()

    if imported:
        _match_after_sync(catalog_path, db_path)
    return code


def import_fab(paths: list[Path], db_path: Path, *, catalog_path: Path = CATALOG_PATH) -> int:
    if not paths:
        print(f"Žádný report z Fabu. Ulož CSV do {FAB_DIR}/ nebo zadej cestu k souboru.")
        return 1
    return _import_reports(
        paths, db_path, label="Fab", parse=fab.parse_report, format_error=fab.FabFormatError,
        catalog_path=catalog_path,
    )


def import_cgtrader(paths: list[Path], db_path: Path, *, catalog_path: Path = CATALOG_PATH) -> int:
    if not paths:
        print(f"Žádný report z CGTraderu. Ulož CSV do {CGTRADER_DIR}/ nebo zadej cestu k souboru.")
        return 1
    sales_paths = []
    for path in paths:
        if cgtrader.is_downloads_report(path):
            print(f"{path.name}: report stažení (Item downloads), ne prodejů – přeskakuji.")
        else:
            sales_paths.append(path)
    if not sales_paths:
        return 0
    return _import_reports(
        sales_paths,
        db_path,
        label="CGTrader",
        parse=cgtrader.parse_report,
        format_error=cgtrader.CgtraderFormatError,
        catalog_path=catalog_path,
    )


def sync_cosmos(
    db_path: Path,
    load_page: Callable[[int], object],
    *,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    catalog_path: Path = CATALOG_PATH,
) -> int:
    """Load Cosmos sales page by page (browser agent, or a fake in tests) and store them."""
    conn = db.connect(db_path)
    try:
        known = {eid.split("|", 1)[0] for eid in db.external_ids(conn, cosmos.MARKETPLACE)}
        try:
            records = cosmos.fetch_pages(
                load_page, known, now=now or datetime.now(UTC), sleep=sleep
            )
        except cosmos.SessionExpired as exc:
            print(
                f"Přihlášení do Cosmosu vypršelo ({exc}). Nic se neuložilo. Přihlas se: "
                f"uv run python -m sales_tracker {daily.COSMOS_LOGIN_HINT}"
            )
            return 1
        except cosmos.FetchError as exc:
            print(f"Načtení prodejů z Cosmosu selhalo: {exc}. Nic se neuložilo.")
            return 1

        sales, skipped, refunded = [], [], []
        for record in records:
            try:
                tx = cosmos.from_api(record)
                sales.extend(cosmos.to_sales(tx))
            except cosmos.SkipTransaction as skip:
                skipped.append(skip)
                continue
            if tx.refunded:
                refunded.append(tx.id)
        result = db.upsert_sales(conn, sales)
    finally:
        conn.close()

    for skip in skipped:
        print(f"Přeskočeno: transakce {skip.tx_id or '(bez ID)'} – {skip.reason}")
    for tx_id in refunded:
        print(
            f"Upozornění: transakce {tx_id} má refund_details – uloženo jako refund, "
            "formát refundu zatím neověřený, zkontroluj ho."
        )
    print(
        f"Cosmos (prohlížeč): transakcí {len(records)}, záznamů {len(sales)}, nových {result.new}, "
        f"aktualizovaných {result.updated}, přeskočeno {len(skipped)}."
    )
    _match_after_sync(catalog_path, db_path)
    return 0


def import_cosmos(paths: list[Path], db_path: Path, *, catalog_path: Path = CATALOG_PATH) -> int:
    """Pasted copies of the Cosmos sales table (fallback path, spec M4a). Never changes known transactions."""
    if not paths:
        print(f"Žádná ruční kopie z Cosmosu. Ulož text do {COSMOS_DIR}/*.txt nebo zadej cestu k souboru.")
        return 1
    catalog = None
    if Path(catalog_path).exists():
        try:
            catalog = catalog_mod.load_catalog(catalog_path)
        except catalog_mod.CatalogError:
            print("Katalog má chyby, ceny pro dělení transakcí s víc produkty nejsou k dispozici.")

    def price_of(sku: str) -> int | None:
        return catalog.price(cosmos.MARKETPLACE, sku) if catalog else None

    code = 0
    imported = False
    conn = db.connect(db_path)
    try:
        for path in paths:
            try:
                text = path.read_bytes().decode("utf-8-sig")
            except FileNotFoundError:
                print(f"Soubor {path} neexistuje.")
                code = 1
                continue
            except UnicodeDecodeError:
                print(f"{path.name}: soubor není v kódování UTF-8. Nic se z něj neuložilo.")
                code = 1
                continue
            transactions, skipped = cosmos.from_paste(text, price_of)
            total = len(transactions) + len(skipped)
            known = {eid.split("|", 1)[0] for eid in db.external_ids(conn, cosmos.MARKETPLACE)}
            fresh = [tx for tx in transactions if tx.id not in known]
            sales = []
            for tx in fresh:
                try:
                    sales.extend(cosmos.to_sales(tx))
                except cosmos.SkipTransaction as skip:
                    skipped.append(skip)
            result = db.upsert_sales(conn, sales)
            imported = True
            for skip in skipped:
                print(f"Přeskočeno: {path.name}, transakce {skip.tx_id or '(bez ID)'} – {skip.reason}")
            print(
                f"Cosmos (ruční kopie, {path.name}): transakcí {total}, "
                f"už v DB {len(transactions) - len(fresh)}, záznamů {len(sales)}, nových {result.new}, "
                f"aktualizovaných {result.updated}, přeskočeno {len(skipped)}."
            )
    finally:
        conn.close()

    if imported:
        _match_after_sync(catalog_path, db_path)
    return code


def cosmos_login() -> int:
    from sales_tracker.cosmos_browser import CosmosBrowser

    print("Otevírám Chrome s profilem pro Cosmos. Přihlas se (máš 10 minut), okno se pak zavře samo.")
    with CosmosBrowser(headless=False) as browser:
        ok = browser.wait_for_login()
    print("Přihlášení do Cosmosu je uložené." if ok else "Přihlášení se nepodařilo, zkus to znovu.")
    return 0 if ok else 1


def run_sync_cosmos() -> int:
    from sales_tracker.cosmos_browser import CosmosBrowser

    with CosmosBrowser() as browser:
        return sync_cosmos(DB_PATH, browser.load_page)


def exclude_sale(db_path: Path, marketplace: str, external_id: str, reason: str | None) -> int:
    conn = db.connect(db_path)
    try:
        found = db.set_excluded(conn, marketplace, external_id, reason)
    finally:
        conn.close()
    if not found:
        print(f"Prodej {marketplace} {external_id} v databázi není. Nic se nezměnilo.")
        return 1
    if reason is None:
        print(f"Prodej {marketplace} {external_id} se zase počítá do součtů.")
    else:
        print(f"Prodej {marketplace} {external_id} se nepočítá do součtů ({reason}).")
    return 0


def run_sync_gumroad(since: date | None = None) -> int:
    # Explicit path: without it python-dotenv searches upwards from this file, not from cwd.
    load_dotenv(Path.cwd() / ".env")
    token = os.environ.get("GUMROAD_ACCESS_TOKEN", "").strip()
    if not token:
        print("Chybí GUMROAD_ACCESS_TOKEN v .env. Zkopíruj .env.example jako .env a doplň token.")
        return 1
    return sync_gumroad(token, DB_PATH, since=since)


def run_import_fab_daily() -> int:
    paths = report_paths(None, FAB_DIR)
    if not paths:
        print(f"Žádný report z Fabu v {FAB_DIR}/, přeskakuji.")
        return 0
    return import_fab(paths, DB_PATH)


def send_report(report: daily.Report) -> None:
    load_dotenv(Path.cwd() / ".env")
    emailer.send_email(
        os.environ.get("RESEND_API_KEY", "").strip(),
        os.environ.get("REPORT_EMAIL_TO", "").strip(),
        report.subject,
        report.text(),
        report.html(),
        sender=os.environ.get("REPORT_EMAIL_FROM", "").strip() or emailer.DEFAULT_FROM,
    )


def run_import_cgtrader_daily() -> int:
    paths = report_paths(None, CGTRADER_DIR)
    if not paths:
        print(f"Žádný report z CGTraderu v {CGTRADER_DIR}/, přeskakuji.")
        return 0
    return import_cgtrader(paths, DB_PATH)


def weekly_config(dry_run: bool, with_claude: bool) -> daily.WeeklyConfig:
    from sales_tracker import weekly

    catalog = None
    if CATALOG_PATH.exists():
        try:
            catalog = catalog_mod.load_catalog(CATALOG_PATH)
        except catalog_mod.CatalogError:
            catalog = None

    def product_name(key: str) -> str:
        try:
            return catalog.name_of(key) if catalog else key
        except KeyError:
            return key

    if dry_run and not with_claude:
        return daily.WeeklyConfig(None, "(zkušební běh: komentář Claude se nevolá)", product_name)
    load_dotenv(Path.cwd() / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return daily.WeeklyConfig(None, "Komentář Claude chybí: chybí ANTHROPIC_API_KEY v .env.", product_name)
    return daily.WeeklyConfig(weekly.ClaudeWriter(key), None, product_name)


def run_daily(dry_run: bool = False, with_claude: bool = False) -> int:
    steps = [
        daily.Step("gumroad", "Gumroad", run_sync_gumroad),
        daily.Step("cosmos", "Cosmos", run_sync_cosmos),
        daily.Step("fab", "Fab", run_import_fab_daily),
        daily.Step("cgtrader", "CGTrader", run_import_cgtrader_daily),
    ]
    return daily.run_daily(
        steps, db_path=DB_PATH, state_path=STATE_PATH, log_dir=LOG_DIR,
        send=None if dry_run else send_report, now=datetime.now(UTC),
        make_rates=lambda conn, today: fx.Rates(conn, today),
        weekly_config=weekly_config(dry_run, with_claude),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sales_tracker")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="stáhne prodeje z marketplace")
    sync.add_argument("marketplace", choices=["gumroad", "cosmos"])
    sync.add_argument("--since", type=_date, help="Gumroad: stáhnout prodeje od data (YYYY-MM-DD)")
    sync.add_argument("--login", action="store_true", help="Cosmos: přihlásit se v okně prohlížeče")
    imp = commands.add_parser("import", help="naimportuje ručně stažený report")
    imp.add_argument("marketplace", choices=["fab", "cgtrader", "cosmos"])
    imp.add_argument("path", nargs="?", type=Path, help="CSV soubor; bez něj všechna CSV ze složky marketplace")
    catalog = commands.add_parser("catalog", help="katalog produktů a párování prodejů")
    catalog.add_argument("action", choices=["check", "match"])
    excl = commands.add_parser("exclude", help="nepočítat prodej do součtů (např. zkušební nákup)")
    excl.add_argument("marketplace", choices=["gumroad", "cosmos", "fab", "cgtrader"])
    excl.add_argument("external_id")
    group = excl.add_mutually_exclusive_group(required=True)
    group.add_argument("--reason", help="proč se nepočítá, např. \"zkušební nákup\"")
    group.add_argument("--undo", action="store_true", help="zase počítat")
    commands.add_parser("demo", help="ukázka na vymyšlených datech, bez účtů a sítě")
    run = commands.add_parser("run", help="denní agent: stáhne vše a pošle ranní souhrn e-mailem")
    run.add_argument("job", choices=["daily"])
    run.add_argument("--dry-run", action="store_true", help="souhrn jen vypsat, e-mail neposílat")
    run.add_argument("--with-claude", action="store_true", help="i při --dry-run zavolat Claude na komentář")
    args = parser.parse_args(argv)
    if args.command == "sync" and args.login and args.marketplace != "cosmos":
        parser.error("--login je jen pro cosmos")
    if args.command == "sync" and args.since and args.marketplace != "gumroad":
        parser.error("--since je jen pro gumroad")

    if args.command == "sync" and args.marketplace == "cosmos":
        return cosmos_login() if args.login else run_sync_cosmos()

    if args.command == "import" and args.marketplace == "cosmos":
        return import_cosmos(report_paths(args.path, COSMOS_DIR, "*.txt"), DB_PATH)
    if args.command == "import" and args.marketplace == "cgtrader":
        return import_cgtrader(report_paths(args.path, CGTRADER_DIR), DB_PATH)
    if args.command == "import":
        return import_fab(report_paths(args.path, FAB_DIR), DB_PATH)

    if args.command == "catalog":
        if args.action == "check":
            return catalog_check(CATALOG_PATH, DB_PATH)
        return catalog_match(CATALOG_PATH, DB_PATH)

    if args.command == "demo":
        from sales_tracker import demo

        return demo.run()

    if args.command == "exclude":
        reason = None if args.undo else args.reason.strip()
        if reason == "":
            parser.error("--reason nesmí být prázdný")
        return exclude_sale(DB_PATH, args.marketplace, args.external_id, reason)

    if args.command == "run":
        if args.with_claude and not args.dry_run:
            parser.error("--with-claude je jen pro --dry-run")
        return run_daily(dry_run=args.dry_run, with_claude=args.with_claude)

    return run_sync_gumroad(args.since)
