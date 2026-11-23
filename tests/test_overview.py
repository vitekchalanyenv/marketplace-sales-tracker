"""Přehled (spec M6): výpočty pro dashboard na vymyšlených datech, bez Streamlitu a bez sítě."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from sales_tracker import daily, db, fx, overview
from sales_tracker.models import Sale, Status

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
TODAY = date(2026, 11, 23)


def sale(marketplace, external_id, net, sold_at, *, quantity=1, status=Status.SOLD, currency="USD",
         title="Vymyšlený produkt"):
    return Sale(
        marketplace=marketplace, external_id=external_id, product_title=title, product_ref=None,
        sold_at=sold_at, gross_cents=abs(net) * 2, net_cents=net, currency=currency, status=status,
        raw={}, quantity=quantity,
    )


class FixedRates:
    """USD 20, EUR 25; days in `missing` have no rate."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.error = None

    def rate(self, day, currency):
        if currency == "CZK":
            return Decimal(1)
        if day in self.missing:
            self.error = "ČNB není dostupná"
            return None
        return {"USD": Decimal(20), "EUR": Decimal(25)}[currency]


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "sales.db")
    yield connection
    connection.close()


def rows(conn, *sales, rates=None):
    db.upsert_sales(conn, sales)
    return overview.load(conn, daily.CzkConverter(rates or FixedRates()))


def at(day, hour=12, minute=0):
    return datetime(2026, *day, hour, minute, tzinfo=UTC)


def test_soucet_v_puvodni_mene_a_v_kc(conn):
    data = rows(conn, sale("gumroad", "a", 1000, at((11, 2))), sale("fab", "b", 250, at((11, 3))))
    value = overview.total(data)
    assert value.units == 2
    assert value.by_currency == {"USD": 1250}
    assert value.czk_complete == 25000  # 12,50 USD × 20 = 250,00 Kč
    assert overview.money(value) == "12,50 USD (≈ 250,00 Kč)"


def test_ruzne_meny_se_nescitaji(conn):
    data = rows(conn, sale("gumroad", "a", 1000, at((11, 2))),
                sale("cosmos", "b", 400, at((11, 3)), currency="EUR"))
    value = overview.total(data)
    assert value.by_currency == {"USD": 1000, "EUR": 400}
    # 10 USD × 20 = 200 Kč, 4 EUR × 25 = 100 Kč
    assert overview.money(value) == "4,00 EUR + 10,00 USD (≈ 300,00 Kč)"


def test_vyloucene_prodeje_se_nepocitaji(conn):
    db.upsert_sales(conn, [sale("gumroad", "test-nakup", 1000, at((11, 2)))])
    db.set_excluded(conn, "gumroad", "test-nakup", "zkušební nákup")
    data = rows(conn, sale("gumroad", "a", 500, at((11, 3))))
    assert [row.external_id for row in data] == ["a"]


def test_refundy_jako_v_emailu(conn):
    data = rows(
        conn,
        sale("gumroad", "a", 1000, at((11, 2))),
        sale("gumroad", "vraceny", 1000, at((11, 3)), status=Status.REFUNDED),  # stav: nepočítá se
        sale("fab", "f1", 800, at((11, 4))),
        sale("fab", "f1-refund", -800, at((11, 5)), quantity=-1),  # záporný řádek: odečte se
    )
    value = overview.total(data)
    assert value.units == 1  # 1 + 1 − 1
    assert value.by_currency == {"USD": 1000}  # 10,00 + 8,00 − 8,00


def test_chybejici_kurz_soucet_v_kc_neni_uplny(conn):
    data = rows(conn, sale("gumroad", "a", 1000, at((11, 2))), sale("fab", "b", 500, at((11, 3))),
                rates=FixedRates(missing={date(2026, 11, 3)}))
    value = overview.total(data)
    assert value.czk_complete is None
    assert overview.money(value) == "15,00 USD (Kč nedostupné, chybí kurz)"


def test_obdobi_podle_mistniho_casu(conn):
    # 31. 10. 23:30 UTC je v Praze už 1. 11. 0:30 → listopad; 31. 10. 22:30 UTC = 23:30 v Praze → říjen
    data = rows(conn, sale("gumroad", "listopad", 100, datetime(2026, 10, 31, 23, 30, tzinfo=UTC)),
                sale("gumroad", "rijen", 200, datetime(2026, 10, 31, 22, 30, tzinfo=UTC)))
    this_month, last_month, this_year = overview.fixed_periods(TODAY)
    assert [r.external_id for r in overview.select(data, this_month)] == ["listopad"]
    assert [r.external_id for r in overview.select(data, last_month)] == ["rijen"]
    assert len(overview.select(data, this_year)) == 2
    assert (last_month.start, last_month.end) == (date(2026, 10, 1), date(2026, 10, 31))


def test_obdobi_v_lednu_saha_do_minuleho_roku():
    _, last_month, this_year = overview.fixed_periods(date(2027, 1, 5))
    assert (last_month.start, last_month.end) == (date(2026, 12, 1), date(2026, 12, 31))
    assert this_year.start == date(2027, 1, 1)
    twelve = overview.filter_periods(date(2027, 1, 5))[3]
    assert twelve.start == date(2026, 2, 1)


def test_filtr_marketplace(conn):
    data = rows(conn, sale("gumroad", "a", 100, at((11, 2))), sale("fab", "b", 200, at((11, 2))))
    everything = overview.Period("Vše", None, None)
    assert [r.marketplace for r in overview.select(data, everything, ["fab"])] == ["fab"]
    assert len(overview.select(data, everything, None)) == 2


def test_podle_marketplace_serazeno_podle_prijmu(conn):
    data = rows(conn, sale("gumroad", "a", 100, at((11, 2))),
                sale("cosmos", "b", 900, at((11, 2))), sale("cosmos", "c", 100, at((11, 3))))
    result = overview.by_marketplace(data)
    assert [(name, value.units) for name, value in result] == [("cosmos", 2), ("gumroad", 1)]


def test_mesice_pro_graf_vcetne_prazdnych(conn):
    data = rows(conn, sale("gumroad", "a", 100, at((9, 2))), sale("fab", "b", 200, at((11, 2))))
    bars = overview.monthly(data)
    assert [(b.month, b.marketplace, b.czk) for b in bars] == [
        ("2026-09", "fab", 0), ("2026-09", "gumroad", 2000),  # 1,00 USD × 20 = 20,00 Kč
        ("2026-10", "fab", 0), ("2026-10", "gumroad", 0),
        ("2026-11", "fab", 4000), ("2026-11", "gumroad", 0),
    ]
    assert not any(b.incomplete for b in bars)


def test_produkty_napric_platformami_a_nesparovane(conn):
    db.upsert_sales(conn, [
        sale("gumroad", "a", 1000, at((11, 2))),
        sale("cosmos", "b", 1500, at((11, 3)), quantity=2),
        sale("fab", "c", 300, at((11, 4)), title="Něco, co v katalogu není"),
    ])
    conn.execute("UPDATE sales SET product_key = 'les' WHERE external_id IN ('a', 'b')")
    data = overview.load(conn, daily.CzkConverter(FixedRates()))
    lines = overview.products(data, {"les": "Vymyšlený les"}.get)
    assert [(line.name, line.matched, line.total.units) for line in lines] == [
        ("Vymyšlený les", True, 3),
        ("nespárováno: Něco, co v katalogu není (Fab)", False, 1),
    ]
    assert lines[0].units_by_marketplace == {"gumroad": 1, "cosmos": 2}
    assert lines[0].total.czk_complete == 50000  # 25,00 USD × 20


def test_poslednich_dvacet_od_nejnovejsiho(conn):
    data = rows(conn, *[sale("gumroad", f"s{n:02d}", 100, at((11, n))) for n in range(1, 23)])
    result = overview.recent(data)
    assert len(result) == 20
    assert result[0].external_id == "s22"
    assert result[-1].external_id == "s03"


def test_cas_prodeje_jako_v_emailu(conn):
    data = rows(conn, sale("cosmos", "a", 100, at((11, 2), 13, 5)), sale("fab", "b", 100, at((11, 2))))
    assert [overview.when(row) for row in data] == ["2. 11. 2026", "2. 11. 2026 14:05"]


def test_stav_zdroju(conn):
    db.upsert_sales(conn, [sale("cosmos", "a", 100, at((11, 2))), sale("fab", "b", 100, at((11, 2)))])
    state = {"last_success": {"gumroad": "2026-11-23T07:00:00+00:00", "cosmos": "2026-11-18T07:00:00+00:00"}}
    result = {s.marketplace: s for s in overview.sources(conn, state, NOW)}
    assert list(result) == ["gumroad", "cosmos", "fab", "cgtrader"]
    assert not result["gumroad"].stale and result["gumroad"].last_sale is None
    assert result["cosmos"].stale  # 5 dní
    assert result["cosmos"].last_sale == at((11, 2))
    assert not result["fab"].automatic and not result["fab"].stale
    assert result["fab"].last_update is not None  # kdy přibyl záznam


def test_kurzy_se_stahuji_s_pauzou(conn):
    pauses, days = [], []

    def fetch(day):
        days.append(day)
        return f"{day:%d.%m.%Y} #1\nzemě|měna|množství|kód|kurz\nUSA|dolar|1|USD|20,000\n"

    rates = fx.Rates(conn, TODAY, fx.polite(fetch, pause=1.0, sleep=pauses.append))
    data = rows(conn, sale("gumroad", "a", 100, at((11, 2))), sale("gumroad", "b", 100, at((11, 2), 15)),
                sale("gumroad", "c", 100, at((11, 3))), rates=rates)
    assert days == [date(2026, 11, 2), date(2026, 11, 3)]  # každý den jednou
    assert pauses == [1.0]  # pauza mezi requesty, ne před prvním
    assert overview.total(data).czk_complete == 6000


def test_vypadek_cnb_nespadne(conn):
    def fetch(day):
        raise fx.FxError("ČNB není dostupná")

    rates = fx.Rates(conn, TODAY, fx.polite(fetch, sleep=lambda s: None))
    data = rows(conn, sale("gumroad", "a", 100, at((11, 2))), rates=rates)
    assert overview.total(data).czk_complete is None
    assert rates.error == "ČNB není dostupná"


def test_zaokrouhleni_na_cele_koruny_a_popisek_mesice(conn):
    data = rows(conn, sale("gumroad", "a", 1, at((11, 2))))  # 0,01 USD × 20 = 0,20 Kč
    assert overview.czk_rounded(overview.total(data)) == "≈ 0 Kč"
    value = overview.Total(czk=549350)
    assert overview.czk_rounded(value) == "≈ 5 494 Kč"  # 5 493,50 → nahoru
    assert overview.month_label("2026-01") == "1/2026"


def test_stav_zdroju_v_demu_neukaze_budoucnost(conn):
    db.upsert_sales(conn, [sale("fab", "b", 100, at((1, 2)))])  # first_seen_at = skutečné „teď“
    past = datetime(2026, 1, 26, 7, 0, tzinfo=UTC)  # pevné „dnes“ dema
    fab = {s.marketplace: s for s in overview.sources(conn, {}, past)}["fab"]
    assert fab.last_update == past
