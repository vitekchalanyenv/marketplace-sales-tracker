"""Demo: the whole pipeline on the made-up data in data/sample/, no accounts, network or .env (spec M5b).

Everything runs in a temporary folder: Gumroad answers from sample JSON through a fake HTTP
transport, Cosmos from sample API pages and a pasted table, Fab and CGTrader from sample CSVs.
Then catalog matching and the morning report, printed instead of e-mailed. "Today" and the
exchange rates are fixed, so the output is the same on every run.
"""

import json
import shutil
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from sales_tracker import cli, daily

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"
NOW = datetime(2026, 1, 26, 7, 0, tzinfo=UTC)  # Monday 8:00 in Prague
RATES = {"USD": Decimal("20.50"), "EUR": Decimal("24.75")}  # made up, not ČNB


class DemoRates:
    error = None

    def rate(self, day: date, currency: str) -> Decimal | None:
        return Decimal(1) if currency == "CZK" else RATES.get(currency)


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


def run(work: Path | None = None) -> int:
    owned = work is None
    work = Path(tempfile.mkdtemp(prefix="sales-tracker-demo-")) if owned else Path(work)
    try:
        db_path = work / "sales.db"
        catalog = work / "katalog.yaml"
        shutil.copy(SAMPLE_DIR / "katalog.yaml", catalog)
        cosmos_pages = {n: _json(f"cosmos_api_page{n}.json") for n in (1, 2)}

        steps = [
            daily.Step("gumroad", "Gumroad", lambda: cli.sync_gumroad(
                "demo-token", db_path, transport=_gumroad_transport(), sleep=lambda s: None,
                today=NOW.date(), catalog_path=catalog,
            )),
            daily.Step("cosmos", "Cosmos", lambda: cli.sync_cosmos(
                db_path, lambda n: cosmos_pages[n], now=NOW, sleep=lambda s: None, catalog_path=catalog,
            )),
            daily.Step("cosmos-paste", "Cosmos (ruční kopie)", lambda: cli.import_cosmos(
                [SAMPLE_DIR / "cosmos_paste.txt"], db_path, catalog_path=catalog,
            )),
            daily.Step("fab", "Fab", lambda: cli.import_fab(
                [SAMPLE_DIR / "fab_report.csv"], db_path, catalog_path=catalog,
            )),
            daily.Step("cgtrader", "CGTrader", lambda: cli.import_cgtrader(
                [SAMPLE_DIR / "cgtrader_report.csv"], db_path, catalog_path=catalog,
            )),
        ]
        print("DEMO – vymyšlená data z data/sample/, nic se nestahuje ani neodesílá.")
        print(f"„Dnes“ je {NOW.astimezone(daily.LOCAL_TZ):%d. %m. %Y %H:%M}, kurzy jsou vymyšlené.\n")
        return daily.run_daily(
            steps, db_path=db_path, state_path=work / "state.json", log_dir=work / "logs",
            send=None, now=NOW, make_rates=lambda conn, today: DemoRates(),
            weekly_config=daily.WeeklyConfig(
                None,
                "(V ostrém běhu sem Claude napíše 2–4 věty komentáře. Než se pošle, kontrola ověří, "
                "že každé číslo v textu je v datech výše.)",
                _product_names(catalog),
            ),
        )
    finally:
        if owned:
            shutil.rmtree(work, ignore_errors=True)
