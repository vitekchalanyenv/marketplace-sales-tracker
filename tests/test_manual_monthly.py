"""Spec M5c: stav ručních zdrojů (Fab, CGTrader) a měsíční shrnutí v ranním e-mailu. Vymyšlená data."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from sales_tracker import daily, db, manual, monthly
from sales_tracker.models import Sale, Status

CG_HEADER = ("OID,Purchased,Product,Product ID,Buyer,Country,Original Price,Sold For,Payment Processing,"
             "After tax,Earning rate,Final Earnings,Transaction ID\n")
CG_DOWNLOADS = "Product ID,Product,Price,Downloader,Download Date,File name\n1,x,$1.00,someone,2026-11-02,a.zip\n"


def cg_row(day: str, oid: str = "1") -> str:
    return f"{oid},{day},https://www.cgtrader.com/3d-models/x/vymysleny,1,kupec,CZ,$10.00,$10.00,$0.50,$9.50,80%,$7.60,t{oid}\n"


def sale(marketplace, external_id, net, sold_at, *, quantity=1, status=Status.SOLD, currency="USD",
         title="Vymyšlený produkt"):
    return Sale(
        marketplace=marketplace, external_id=external_id, product_title=title, product_ref=None,
        sold_at=sold_at, gross_cents=abs(net) * 2, net_cents=net, currency=currency, status=status,
        raw={}, quantity=quantity,
    )


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "sales.db")
    yield connection
    connection.close()


# --- Fab ----------------------------------------------------------------------------------------

def test_fab_konec_obdobi_z_nazvu_souboru(tmp_path, conn):
    (tmp_path / "2026-01-01_2026-11-10_fab_daily_sales_report.csv").write_text("")
    (tmp_path / "2026-10-01_2026-11-20_fab_daily_sales_report.csv").write_text("")
    assert manual.fab_until(tmp_path, conn) == (date(2026, 11, 20), True)


def test_fab_nazev_mimo_format_podle_posledniho_prodeje(tmp_path, conn):
    (tmp_path / "muj_report.csv").write_text("")
    db.upsert_sales(conn, [sale("fab", "f", 100, datetime(2026, 11, 14, 23, 30, tzinfo=UTC))])  # 15. 11. v Praze
    assert manual.fab_until(tmp_path, conn) == (date(2026, 11, 15), False)
    status = manual.fab_status(date(2026, 11, 15), False, date(2026, 11, 18))
    assert status.text == "ok – data do 15. 11. (podle posledního prodeje)"


def test_fab_varovani_od_sedmi_dni():
    assert not manual.fab_status(date(2026, 11, 17), True, date(2026, 11, 23)).warning  # 6 dní
    stale = manual.fab_status(date(2026, 11, 16), True, date(2026, 11, 23))  # 7 dní
    assert stale.warning and stale.in_subject
    assert stale.text == "⚠ data jen do 16. 11. (7 dní), stáhni nový report"


def test_fab_bez_reportu(tmp_path, conn):
    assert manual.fab_status(*manual.fab_until(tmp_path / "neni", conn), date(2026, 11, 23)).warning


# --- CGTrader ----------------------------------------------------------------------------------

def test_cgtrader_mesic_z_reportu_bez_reportu_stazeni(tmp_path):
    (tmp_path / "2026-07.csv").write_text(CG_HEADER + cg_row("2026-07-30"), encoding="utf-8")
    (tmp_path / "2026-10.csv").write_text(CG_HEADER + cg_row("2026-10-13", "2"), encoding="utf-8")
    (tmp_path / "stazeni.csv").write_text(CG_DOWNLOADS, encoding="utf-8")  # listopad, ale jen stažení
    assert manual.cgtrader_until(tmp_path) == (2026, 10)


def test_cgtrader_varovani_az_po_desatem():
    assert not manual.cgtrader_status((2026, 10), date(2026, 12, 10)).warning
    late = manual.cgtrader_status((2026, 10), date(2026, 12, 11))
    assert late.warning and not late.in_subject
    assert late.text == "⚠ chybí report za listopad 2026"
    assert manual.cgtrader_status((2026, 11), date(2026, 12, 20)).text == "ok – reporty do listopadu 2026"
    assert manual.cgtrader_status((2025, 12), date(2026, 1, 11)).text == "ok – reporty do prosince 2025"


# --- v e-mailu ----------------------------------------------------------------------------------

def ok_step(key, name):
    return daily.Step(key, name, lambda: 0)


def run(tmp_path, now, steps=(), **kwargs):
    sent = []
    code = daily.run_daily(
        list(steps), db_path=tmp_path / "sales.db", state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs", send=sent.append, now=now, **kwargs,
    )
    return code, sent


def lines(report, title_start):
    return next(s.lines for s in report.sections if s.title.startswith(title_start))


def test_stav_rucnich_zdroju_v_emailu_a_predmetu(tmp_path):
    fab_dir, cg_dir = tmp_path / "fab", tmp_path / "cg"
    fab_dir.mkdir(), cg_dir.mkdir()
    (fab_dir / "2026-10-01_2026-11-10_fab_daily_sales_report.csv").write_text("")
    (cg_dir / "r.csv").write_text(CG_HEADER + cg_row("2026-10-13"), encoding="utf-8")
    _, sent = run(tmp_path, datetime(2026, 11, 23, 7, 0, tzinfo=UTC),
                  [ok_step("fab", "Fab"), ok_step("cgtrader", "CGTrader")], manual_dirs=(fab_dir, cg_dir))
    report = sent[0]
    assert lines(report, "Stav zdrojů") == [
        "Fab: ⚠ data jen do 10. 11. (13 dní), stáhni nový report",
        "CGTrader: ok – reporty do října 2026",
    ]
    assert "⚠ starý report: Fab" in report.subject


def test_chyba_importu_ma_prednost_pred_stavem(tmp_path):
    fab_dir = tmp_path / "fab"
    fab_dir.mkdir()
    broken = daily.Step("fab", "Fab", lambda: print("neočekávaná hlavička") or 1)
    _, sent = run(tmp_path, datetime(2026, 11, 23, 7, 0, tzinfo=UTC), [broken],
                  manual_dirs=(fab_dir, tmp_path / "cg"))
    assert lines(sent[0], "Stav zdrojů")[0] == "Fab: CHYBA – neočekávaná hlavička"
    assert "starý report" not in sent[0].subject  # už hlásí chyba


# --- měsíční shrnutí ----------------------------------------------------------------------------

class FixedRates:
    error = None

    def rate(self, day, currency):
        return {"CZK": Decimal(1), "USD": Decimal(20), "EUR": Decimal(25)}[currency]


def store(tmp_path, *sales):
    conn = db.connect(tmp_path / "sales.db")
    db.upsert_sales(conn, sales)
    conn.close()


def at(month, day, year=2026):
    return datetime(year, month, day, 12, 0, tzinfo=UTC)


def test_mesicni_shrnuti_cisla(tmp_path):
    store(
        tmp_path,
        sale("cosmos", "c1", 1000, at(10, 5)), sale("cosmos", "c2", 1000, at(10, 6)),
        sale("gumroad", "g1", 400, at(10, 7), currency="EUR"),
        sale("gumroad", "vraceno", 900, at(10, 8), status=Status.REFUNDED),  # nepočítá se
        sale("fab", "f1", 500, at(10, 9)), sale("fab", "f1r", -500, at(10, 10), quantity=-1),  # odečte se
        sale("cosmos", "zari", 1000, at(9, 15)),
        sale("cosmos", "leden", 500, at(1, 15)),
        sale("cosmos", "listopad", 700, at(11, 2)),  # tento měsíc, do shrnutí nepatří
        sale("gumroad", "test", 5000, at(10, 11)),
    )
    conn = db.connect(tmp_path / "sales.db")
    db.set_excluded(conn, "gumroad", "test", "zkušební nákup")
    section = monthly.section(conn, daily.CzkConverter(FixedRates()), date(2026, 11, 3), lambda k: k)
    conn.close()
    assert section.title == "Minulý měsíc (říjen 2026)"
    assert section.lines == [
        # 20 USD × 20 = 400 Kč, 4 EUR × 25 = 100 Kč; Fab 5 − 5 USD = 0
        "Celkem: 3 ks, čistě 4,00 EUR + 20,00 USD (≈ 500,00 Kč)",
        "Cosmos: 2 ks, čistě 20,00 USD (≈ 400,00 Kč)",
        "Gumroad: 1 ks, čistě 4,00 EUR (≈ 100,00 Kč)",
        "Fab: 0 ks, čistě 0,00 USD (≈ 0,00 Kč)",
        "Září 2026: 1 ks, ≈ 200,00 Kč (změna +150 %)",  # 500 proti 200
        "Letos celkem: 5 ks, čistě 4,00 EUR + 35,00 USD (≈ 800,00 Kč)",  # leden 5 + září 10 + říjen 20 USD
    ]


def test_mesicni_shrnuti_nejlepsi_produkt(tmp_path):
    store(tmp_path, sale("cosmos", "a", 1000, at(10, 5)), sale("fab", "b", 300, at(10, 6)),
          sale("fab", "c", 300, at(10, 7)))
    conn = db.connect(tmp_path / "sales.db")
    conn.execute("UPDATE sales SET product_key = 'les' WHERE external_id = 'a'")
    conn.execute("UPDATE sales SET product_key = 'hrad' WHERE external_id IN ('b', 'c')")
    section = monthly.section(conn, daily.CzkConverter(FixedRates()), date(2026, 11, 1),
                              {"les": "Vymyšlený les", "hrad": "Vymyšlený hrad"}.get)
    conn.close()
    assert "Nejlepší produkt: Vymyšlený les (1 ks, ≈ 200,00 Kč)" in section.lines  # podle Kč, ne kusů


def test_leden_shrnuje_prosinec_a_cely_rok(tmp_path):
    store(tmp_path, sale("cosmos", "a", 1000, at(12, 5, 2025)), sale("cosmos", "b", 1000, at(3, 5, 2025)))
    conn = db.connect(tmp_path / "sales.db")
    section = monthly.section(conn, daily.CzkConverter(FixedRates()), date(2026, 1, 2), lambda k: k)
    conn.close()
    assert section.title == "Minulý měsíc (prosinec 2025)"
    assert section.lines[-2] == "Listopad 2025: 0 ks, ≈ 0,00 Kč"
    assert section.lines[-1] == "Rok 2025 celkem: 2 ks, čistě 20,00 USD (≈ 400,00 Kč)"


def test_mesic_bez_prodeju(tmp_path):
    conn = db.connect(tmp_path / "sales.db")
    section = monthly.section(conn, daily.CzkConverter(FixedRates()), date(2026, 11, 1), lambda k: k)
    conn.close()
    assert section.lines[0] == "Celkem: 0 ks, žádné prodeje"


def test_mesicni_sekce_jen_v_prvnim_emailu_mesice(tmp_path):
    rates = {"make_rates": lambda conn, today: FixedRates(), "monthly": True}
    # 1. 11. je PC vypnuté, první e-mail měsíce přijde 2. 11.
    _, sent = run(tmp_path, datetime(2026, 11, 2, 7, 0, tzinfo=UTC), **rates)
    assert sent[0].sections[0].title == "Minulý měsíc (říjen 2026)"
    assert sent[0].subject.endswith("· měsíční shrnutí")
    _, sent = run(tmp_path, datetime(2026, 11, 3, 7, 0, tzinfo=UTC), **rates)
    assert not any(s.title.startswith("Minulý měsíc") for s in sent[0].sections)
    _, sent = run(tmp_path, datetime(2026, 12, 1, 7, 0, tzinfo=UTC), **rates)
    assert sent[0].sections[0].title == "Minulý měsíc (listopad 2026)"


def test_neodeslany_email_mesicni_sekci_zopakuje(tmp_path):
    def broken(report):
        raise OSError("síť nejde")

    daily.run_daily([], db_path=tmp_path / "sales.db", state_path=tmp_path / "state.json",
                    log_dir=tmp_path / "logs", send=broken, now=datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
                    monthly=True)
    _, sent = run(tmp_path, datetime(2026, 11, 2, 7, 0, tzinfo=UTC), monthly=True)
    assert sent[0].sections[0].title == "Minulý měsíc (říjen 2026)"


def test_mesicni_a_tydenni_v_pondeli_prvniho(tmp_path):
    weekly = daily.WeeklyConfig(None, "bez komentáře")
    _, sent = run(tmp_path, datetime(2027, 3, 1, 7, 0, tzinfo=UTC), monthly=True, weekly_config=weekly)
    titles = [s.title for s in sent[0].sections]
    assert titles[0].startswith("Minulý měsíc") and titles[1].startswith("Minulý týden")
    assert sent[0].subject.endswith("· měsíční shrnutí · týdenní shrnutí")
