"""Demo: the whole pipeline on the made-up data in data/sample/, no accounts, network or .env (spec M5b).

Everything runs in a temporary folder: Gumroad answers from sample JSON through a fake HTTP
transport, Cosmos from sample API pages and a pasted table, Fab and CGTrader from sample CSVs.
"Yesterday's" run is replayed silently first, so the morning report shows only what is new since
then. The weekly commentary is a fixed example, not Claude, but it goes through the same check –
and its first version is wrong on purpose, to show a rejection. "Today" and the exchange rates are
fixed, so the output is the same on every run.
"""

import io
import json
import shutil
import tempfile
from contextlib import redirect_stdout
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from sales_tracker import cli, daily, db

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"
NOW = datetime(2026, 1, 26, 7, 0, tzinfo=UTC)  # Monday 8:00 in Prague
YESTERDAY = datetime(2026, 1, 25, 7, 0, tzinfo=UTC)
NEW_SINCE = "2026-01-19T23:00:00Z"  # sales from 20. 1. (local) on are new since yesterday's report
RATES = {"USD": Decimal("20.50"), "EUR": Decimal("24.75")}  # made up, not ČNB

DEMO_BAD = "Cosmos přinesl {cgtrader_kc} a prodeje vzrostly."
DEMO_GOOD = (
    "Za týden {obdobi}: {celkem_kusu} za {celkem_kc}. Hlavním kanálem byl "
    "{nejlepsi_marketplace} s příjmem {cosmos_kc}, z produktů vedl {nejprodavanejsi_produkt}. "
    "Proti týdnu předtím příjem {smer_prijmu} o {zmena_procent}."
)


class DemoRates:
    error = None

    def rate(self, day: date, currency: str) -> Decimal | None:
        return Decimal(1) if currency == "CZK" else RATES.get(currency)


def demo_writer(available, rejected):
    """Stands in for Claude: a wrong first version (the check rejects it), then a correct one."""
    return DEMO_BAD if rejected is None else DEMO_GOOD


def _json(name: str):
    return json.loads((SAMPLE_DIR / name).read_text(encoding="utf-8"))


def _gumroad_transport() -> httpx.MockTransport:
    pages = [_json("gumroad_sales.json"), _json("gumroad_sales_page2.json")]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[1] if "page_key" in request.url.params else pages[0])

    return httpx.MockTransport(handler)


def _product_names(catalog_path: Path):
    from sales_tracker.catalog import load_catalog

    catalog = load_catalog(catalog_path)
    return lambda key: catalog.name_of(key) if key in {p.key for p in catalog.products} else key


def _steps(db_path: Path, catalog: Path, now: datetime) -> list[daily.Step]:
    cosmos_pages = {n: _json(f"cosmos_api_page{n}.json") for n in (1, 2)}
    return [
        daily.Step("gumroad", "Gumroad", lambda: cli.sync_gumroad(
            "demo-token", db_path, transport=_gumroad_transport(), sleep=lambda s: None,
            today=now.date(), catalog_path=catalog, match=False,
        )),
        daily.Step("cosmos", "Cosmos", lambda: cli.sync_cosmos(
            db_path, lambda n: cosmos_pages[n], now=now, sleep=lambda s: None, catalog_path=catalog,
            match=False,
        )),
        daily.Step("cosmos-paste", "Cosmos (ruční kopie)", lambda: cli.import_cosmos(
            [SAMPLE_DIR / "cosmos_paste.txt"], db_path, catalog_path=catalog, match=False,
        )),
        daily.Step("fab", "Fab", lambda: cli.import_fab(
            [SAMPLE_DIR / "fab_report.csv"], db_path, catalog_path=catalog, match=False,
        )),
        daily.Step("cgtrader", "CGTrader", lambda: cli.import_cgtrader(
            [SAMPLE_DIR / "cgtrader_report.csv"], db_path, catalog_path=catalog, match=False,
        )),
        daily.Step("catalog", "Párování s katalogem", lambda: cli.match_step(catalog, db_path)),
    ]


def run(work: Path | None = None, send: daily.Send | None = None) -> int:
    """send: receives the report instead of printing only (the README screenshot uses this)."""
    owned = work is None
    work = Path(tempfile.mkdtemp(prefix="sales-tracker-demo-")) if owned else Path(work)
    try:
        db_path = work / "sales.db"
        catalog = work / "katalog.yaml"
        shutil.copy(SAMPLE_DIR / "katalog.yaml", catalog)
        common = {
            "db_path": db_path, "state_path": work / "state.json", "log_dir": work / "logs",
            "make_rates": lambda conn, today: DemoRates(),
        }

        # Yesterday's report, not shown: everything up to 19. 1. was already reported then.
        with redirect_stdout(io.StringIO()):
            daily.run_daily(
                _steps(db_path, catalog, YESTERDAY), send=lambda r: None, now=YESTERDAY, **common
            )
        conn = db.connect(db_path)
        with conn:
            conn.execute("DELETE FROM sales WHERE sold_at >= ?", (NEW_SINCE,))
        # SQLite reuses the rowids of deleted rows, so the "reported" baseline must follow the delete.
        # (The real tool never deletes sales, so this only concerns the demo.)
        state = json.loads((work / "state.json").read_text(encoding="utf-8"))
        state["reported"] = {}
        daily._save_reported(state, daily.snapshot(conn))
        (work / "state.json").write_text(json.dumps(state), encoding="utf-8")
        conn.close()

        print("DEMO – vymyšlená data z data/sample/, nic se nestahuje ani neodesílá.")
        print(f"„Dnes“ je {NOW.astimezone(daily.LOCAL_TZ):%d. %m. %Y %H:%M}, kurzy jsou vymyšlené, "
              "komentář je ukázkový (ne od Claude), ale prošel stejnou kontrolou.\n")
        return daily.run_daily(
            _steps(db_path, catalog, NOW), send=send, now=NOW,
            weekly_config=daily.WeeklyConfig(
                demo_writer, None, _product_names(catalog),
                label="Ukázkový komentář (ne od Claude)",
            ),
            **common,
        )
    finally:
        if owned:
            shutil.rmtree(work, ignore_errors=True)
