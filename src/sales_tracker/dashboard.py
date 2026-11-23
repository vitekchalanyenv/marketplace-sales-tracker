"""The dashboard page (spec M6). Started by `python -m sales_tracker dashboard` through Streamlit.

All numbers come from overview.py; this module only draws them. Configuration comes from
environment variables set by the command, so the page can also be tested with Streamlit's AppTest.
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

ENV_DB = "SALES_TRACKER_DB"
ENV_STATE = "SALES_TRACKER_STATE"
ENV_CATALOG = "SALES_TRACKER_CATALOG"
ENV_DEMO = "SALES_TRACKER_DEMO"  # "1" = made-up data: fixed "today" and rates, no ČNB
APP = Path(__file__).with_name("dashboard_app.py")
CACHE_SECONDS = 600


@dataclass(frozen=True)
class Config:
    db_path: Path
    state_path: Path
    catalog_path: Path
    demo: bool


def config_from_env() -> Config:
    return Config(
        Path(os.environ[ENV_DB]), Path(os.environ[ENV_STATE]), Path(os.environ[ENV_CATALOG]),
        os.environ.get(ENV_DEMO) == "1",
    )


# --- launching ----------------------------------------------------------------------------------

def command(port: int | None = None) -> list[str]:
    """Streamlit only on this computer, without its usage statistics (default is on) and headless:
    otherwise its first start in a terminal waits for an answer to a newsletter e-mail prompt.
    The browser is opened by launch() instead."""
    args = [
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--client.toolbarMode", "minimal",  # no "Deploy" button: this page is never published
    ]
    if port is not None:
        args += ["--server.port", str(port)]
    return args


def environment(config: Config) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        ENV_DB: str(config.db_path.resolve()), ENV_STATE: str(config.state_path.resolve()),
        ENV_CATALOG: str(config.catalog_path.resolve()), ENV_DEMO: "1" if config.demo else "0",
    })
    return env


def wait_until_up(url: str, seconds: float = 30) -> bool:
    import time

    import httpx

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def launch(config: Config, port: int | None = None, open_browser: bool = True) -> int:
    import subprocess
    import webbrowser

    url = f"http://127.0.0.1:{port or 8501}"
    server = subprocess.Popen(command(port), env=environment(config), stdin=subprocess.DEVNULL)
    try:
        if wait_until_up(url):
            print(f"Přehled běží na {url} – ukončíš Ctrl+C.")
            if open_browser:
                webbrowser.open(url)
        else:
            print(f"Přehled se do 30 s nespustil, zkus otevřít {url} ručně.")
        return server.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=10)


def run_demo(port: int | None = None, open_browser: bool = True) -> int:
    """The demo's made-up database, then the dashboard on it (data/private/ is never touched)."""
    from sales_tracker import demo

    with tempfile.TemporaryDirectory(prefix="sales-tracker-demo-") as folder:
        work = Path(folder)
        demo.run(work=work)
        return launch(Config(work / "sales.db", work / "state.json", work / "katalog.yaml", True),
                      port, open_browser)


# --- data ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Data:
    rows: list
    sources: list
    today: date
    rate_error: str | None
    loaded_at: datetime


def _product_names(catalog_path: Path):
    from sales_tracker import catalog as catalog_mod

    try:
        catalog = catalog_mod.load_catalog(catalog_path)
        keys = {p.key for p in catalog.products}
    except (FileNotFoundError, catalog_mod.CatalogError):
        return lambda key: key
    return lambda key: catalog.name_of(key) if key in keys else key


def load_data(config: Config) -> Data:
    from sales_tracker import daily, db, demo, fx, overview

    now = demo.NOW if config.demo else datetime.now(UTC)
    today = daily._local(now).date()
    conn = db.connect(config.db_path)
    try:
        rates = demo.DemoRates() if config.demo else fx.Rates(conn, today, fx.polite(fx.fetch_cnb))
        rows = overview.load(conn, daily.CzkConverter(rates))
        try:
            state = json.loads(config.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            state = {}
        sources = overview.sources(conn, state, now)
    finally:
        conn.close()
    return Data(rows, sources, today, rates.error, now)


# --- the page -----------------------------------------------------------------------------------

def render() -> None:
    import pandas as pd
    import streamlit as st

    from sales_tracker import daily, overview

    config = config_from_env()
    st.set_page_config(page_title="Přehled prodejů", layout="wide")

    @st.cache_data(ttl=CACHE_SECONDS, show_spinner="Načítám prodeje a kurzy ČNB…")
    def cached(config: Config) -> Data:
        return load_data(config)

    data = cached(config)
    name = daily._name
    product_name = _product_names(config.catalog_path)

    st.title("Přehled prodejů")
    if config.demo:
        st.info("Demo: vymyšlená data z data/sample/, pevné „dnes“ a vymyšlené kurzy.")
    st.caption(
        f"Data k {daily._local(data.loaded_at):%d. %m. %Y %H:%M}. Čistý příjem po poplatcích, bez "
        "vyloučených prodejů. Kč podle kurzu ČNB ke dni prodeje."
    )
    if data.rate_error:
        st.warning(f"Kurz ČNB nedostupný ({data.rate_error}), součty v Kč nejsou úplné.")

    # filters
    all_marketplaces = list(daily.MARKETPLACE_NAMES)
    with st.sidebar:
        st.header("Filtr")
        periods = overview.filter_periods(data.today)
        labels = [p.label for p in periods] + ["Vlastní rozsah"]
        choice = st.selectbox("Období", labels, index=labels.index("Vše"))
        if choice == "Vlastní rozsah":
            first = data.rows[0].day if data.rows else data.today
            picked = st.date_input("Od – do", (first, data.today), format="DD.MM.YYYY")
            start, end = (picked if isinstance(picked, tuple) and len(picked) == 2 else (first, data.today))
            period = overview.Period("Vlastní rozsah", start, end)
        else:
            period = periods[labels.index(choice)]
        marketplaces = st.multiselect(
            "Marketplace", all_marketplaces, default=all_marketplaces, format_func=name
        )
        if st.button("Načíst znovu"):
            cached.clear()
            st.rerun()

    in_marketplaces = [row for row in data.rows if row.marketplace in marketplaces]
    filtered = overview.select(in_marketplaces, period)

    # 1. fixed periods
    fixed = overview.fixed_periods(data.today)
    columns = st.columns(len(fixed))
    per_period = []
    for column, fixed_period in zip(columns, fixed, strict=True):
        selected = overview.select(in_marketplaces, fixed_period)
        value = overview.total(selected)
        per_period.append(dict(overview.by_marketplace(selected)))
        with column:
            st.metric(fixed_period.label, overview.czk_rounded(value))
            st.caption(f"{value.units} ks · {overview.money(value)}")
    table = []
    for marketplace in all_marketplaces:
        if marketplace not in marketplaces:
            continue
        line = {"Marketplace": name(marketplace)}
        for fixed_period, values in zip(fixed, per_period, strict=True):
            value = values.get(marketplace)
            line[fixed_period.label] = f"{value.units} ks · {overview.money(value)}" if value else "–"
        table.append(line)
    st.dataframe(pd.DataFrame(table), hide_index=True)

    # 2. in time
    st.subheader(f"Příjem po měsících v Kč ({period.label.lower()})")
    bars = overview.monthly(filtered)
    if bars:
        import altair as alt

        chart = pd.DataFrame({
            "Měsíc": [overview.month_label(b.month) for b in bars],
            "Marketplace": [name(b.marketplace) for b in bars],
            # chart only: haléře → koruny as a number for drawing; every total shown as text stays exact
            "Kč": [b.czk / 100 for b in bars],
        })
        order = list(dict.fromkeys(chart["Měsíc"]))
        st.altair_chart(
            alt.Chart(chart).mark_bar().encode(
                x=alt.X("Měsíc:N", sort=order, axis=alt.Axis(labelAngle=0, title=None)),
                y=alt.Y("sum(Kč):Q", title="Kč", axis=alt.Axis(
                    labelExpr="replace(format(datum.value, ',.0f'), ',', ' ')"
                )),
                color=alt.Color("Marketplace:N", sort=[name(m) for m in all_marketplaces]),
                tooltip=["Měsíc", "Marketplace", alt.Tooltip("Kč:Q", format=",.2f")],
            ).properties(height=320),
        )
        if any(b.incomplete for b in bars):
            st.caption("U některých měsíců chybí kurz ČNB, sloupce jsou nižší, než by měly být.")
    else:
        st.write("V tomto období žádné prodeje.")

    # 3. products
    st.subheader("Produkty napříč platformami")
    lines = overview.products(filtered, product_name)
    if lines:
        st.dataframe(pd.DataFrame([
            {
                "Produkt": line.name,
                "Kusy": line.total.units,
                "Kč": overview.czk_text(line.total),
                "Původní měna": overview.money(line.total).split(" (")[0],
                "Kde se prodává": ", ".join(
                    f"{name(m)} {units} ks" for m, units in sorted(
                        line.units_by_marketplace.items(), key=lambda item: (-item[1], item[0])
                    )
                ),
            }
            for line in lines
        ]), hide_index=True)
    else:
        st.write("V tomto období žádné prodeje.")

    # 4. recent sales
    st.subheader(f"Posledních {overview.RECENT} prodejů")
    latest = overview.recent(filtered)
    if latest:
        st.dataframe(height=35 * (len(latest) + 1) + 3, hide_index=True, data=pd.DataFrame([
            {
                "Kdy": overview.when(row),
                "Produkt": product_name(row.product_key) if row.product_key else (row.title or "(bez názvu)"),
                "Marketplace": name(row.marketplace),
                "Kusy": row.quantity,
                "Čistě": daily.format_money(row.net_cents, row.currency),
                "Kč": overview.czk_text(overview.total([row])),
            }
            for row in latest
        ]))
    else:
        st.write("V tomto období žádné prodeje.")

    # 5. sources
    st.subheader("Stav zdrojů")

    def moment(value: datetime | None, marketplace: str) -> str:
        if value is None:
            return "–"
        local = daily._local(value)
        clock = "" if marketplace in daily.DAY_ONLY else f" {local:%H:%M}"
        return f"{local.day}. {local.month}. {local.year}{clock}"

    st.dataframe(pd.DataFrame([
        {
            "Marketplace": name(s.marketplace),
            "Poslední prodej": moment(s.last_sale, s.marketplace),
            "Aktualizace": ("stahuje denní agent, naposledy " if s.automatic else "ruční import, naposledy ")
            + (f"{daily._local(s.last_update):%d. %m. %Y %H:%M}" if s.last_update else "nikdy"),
            "Stav": f"⚠ starší než {daily.STALE_DAYS} dny" if s.stale else "ok",
        }
        for s in data.sources
    ]), hide_index=True)
