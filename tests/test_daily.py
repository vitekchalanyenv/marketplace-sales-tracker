"""Denní agent (spec M5): kroky jsou podvržené funkce, e-maily se jen zaznamenají."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from sales_tracker import daily, db
from sales_tracker.models import Sale, Status

NOW = datetime(2026, 11, 22, 7, 0, tzinfo=UTC)  # 8:00 v Praze


def sale(marketplace, external_id, net, *, quantity=1, status=Status.SOLD, currency="USD",
         sold_at=NOW - timedelta(hours=5), title="Vymyšlený produkt"):
    return Sale(
        marketplace=marketplace, external_id=external_id, product_title=title,
        product_ref=None, sold_at=sold_at, gross_cents=net * 2, net_cents=net, currency=currency,
        status=status, raw={}, quantity=quantity,
    )


class Env:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.db = tmp_path / "sales.db"
        self.sent = []
        self.fail_send = False

    def send(self, report):
        if self.fail_send:
            raise OSError("síť nejde")
        self.sent.append(report)

    def run(self, steps, now=NOW, dry_run=False):
        return daily.run_daily(
            steps, db_path=self.db, state_path=self.tmp / "state.json", log_dir=self.tmp / "logs",
            send=None if dry_run else self.send, now=now,
        )

    def store(self, *sales):
        conn = db.connect(self.db)
        try:
            db.upsert_sales(conn, sales)
        finally:
            conn.close()

    def step(self, *sales):
        def run():
            self.store(*sales)
            print("hotovo")
            return 0
        return run

    def last(self):
        report = self.sent[-1]
        return report.subject, report.text()

    def state(self):
        return json.loads((self.tmp / "state.json").read_text(encoding="utf-8"))

    def log(self, day="2026-11-22"):
        return (self.tmp / "logs" / f"daily_{day}.log").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def ok_step():
    print("nic nového")
    return 0


def test_souhrn_prijde_i_bez_prodeju(env):
    steps = [daily.Step("gumroad", "Gumroad", ok_step), daily.Step("cosmos", "Cosmos", ok_step)]
    assert env.run(steps) == 0
    subject, text = env.last()
    assert subject == "Prodeje 22. 11.: bez nových prodejů"
    assert "Žádné nové prodeje." in text
    assert "Gumroad: ok" in text and "Cosmos: ok" in text
    assert "TENTO MĚSÍC (LISTOPAD 2026)" in text and "Zatím žádné prodeje." in text
    assert "nic nového" in env.log() and "e-mail odeslán" in env.log()


def test_nove_prodeje_po_kusech_a_v_predmetu(env):
    steps = [
        daily.Step("gumroad", "Gumroad", env.step(sale("gumroad", "g1", 1000, title="Chata"))),
        daily.Step("cosmos", "Cosmos", env.step(
            sale("cosmos", "c1", 1225, title="Stadion"), sale("cosmos", "c2", 25, title="Aréna"),
        )),
    ]
    env.run(steps)
    subject, text = env.last()
    assert subject == "Prodeje 22. 11.: 3 nové prodeje, čistě 22,50 USD"
    assert "Cosmos – Stadion – 1× – čistě 12,25 USD (22. 11. 03:00)" in text
    assert "Gumroad – Chata – 1× – čistě 10,00 USD" in text
    assert "Celkem: čistě 22,50 USD" in text
    assert "<li>Cosmos – Stadion" in env.sent[-1].html()


def test_druhy_souhrn_uz_prodeje_nevypise(env):
    step = env.step(sale("gumroad", "g1", 1000))
    env.run([daily.Step("gumroad", "Gumroad", step)])
    env.run([daily.Step("gumroad", "Gumroad", step)], now=NOW + timedelta(days=1))
    subject, text = env.last()
    assert "bez nových prodejů" in subject
    assert "Gumroad: 1 ks, čistě 10,00 USD" in text  # měsíční součet zůstává


def test_prodej_stazeny_rucne_mezi_souhrny(env):
    env.run([daily.Step("gumroad", "Gumroad", ok_step)])
    env.store(sale("cosmos", "c1", 500))  # Vítek spustil sync cosmos ručně
    env.run([daily.Step("gumroad", "Gumroad", ok_step)], now=NOW + timedelta(days=1))
    assert "1 nový prodej, čistě 5,00 USD" in env.last()[0]


def test_prvni_beh_nevypise_celou_historii(env):
    env.store(sale("cosmos", "stary", 500))
    env.run([daily.Step("gumroad", "Gumroad", ok_step)])
    assert "bez nových prodejů" in env.last()[0]


def test_neodeslany_souhrn_se_zopakuje(env):
    env.fail_send = True
    assert env.run([daily.Step("gumroad", "Gumroad", env.step(sale("gumroad", "g1", 1000)))]) == 1
    assert env.sent == []
    assert "E-MAIL SE NEPOSLAL: síť nejde" in env.log()
    env.fail_send = False
    env.run([daily.Step("gumroad", "Gumroad", ok_step)], now=NOW + timedelta(days=1))
    assert "1 nový prodej" in env.last()[0]


def test_refund(env):
    env.run([daily.Step("cosmos", "Cosmos", env.step(sale("cosmos", "c1", 1000, title="Chata")))])
    refunded = sale("cosmos", "c1", 1000, status=Status.REFUNDED, title="Chata")
    env.run([daily.Step("cosmos", "Cosmos", env.step(refunded))], now=NOW + timedelta(days=1))
    subject, text = env.last()
    assert "bez nových prodejů" in subject
    assert "REFUNDY\n- Cosmos – Chata" in text
    assert "Zatím žádné prodeje." in text  # refundovaný prodej se do měsíce nepočítá


def test_mesicni_soucet(env):
    october = datetime(2026, 10, 31, 22, 30, tzinfo=UTC)  # 31. 10. 23:30 v Praze = říjen
    november = datetime(2026, 10, 31, 23, 30, tzinfo=UTC)  # 1. 11. 0:30 v Praze = listopad
    env.store(
        sale("cosmos", "rijen", 999, sold_at=october),
        sale("cosmos", "listopad", 1000, sold_at=november),
        sale("fab", "f1", 880, quantity=2),
        sale("fab", "f1-refund", -440, quantity=-1, status=Status.REFUNDED),
        sale("gumroad", "eur", 300, currency="EUR"),
    )
    env.run([daily.Step("gumroad", "Gumroad", ok_step)])
    text = env.last()[1]
    assert "Cosmos: 1 ks, čistě 10,00 USD" in text
    assert "Fab: 1 ks, čistě 4,40 USD" in text
    assert "Celkem: čistě 14,40 USD" in text
    assert "Gumroad: 1 ks, čistě 3,00 EUR" in text and "Celkem: čistě 3,00 EUR" in text


def test_vyprsene_prihlaseni_cosmos(env):
    def cosmos_step():
        print("Přihlášení do Cosmosu vypršelo (x). Nic se neuložilo. Přihlas se: "
              "uv run python -m sales_tracker sync cosmos --login")
        return 1

    steps = [daily.Step("cosmos", "Cosmos", cosmos_step), daily.Step("gumroad", "Gumroad", ok_step)]
    assert env.run(steps) == 1
    subject, text = env.last()
    assert subject == "Prodeje 22. 11.: ⚠ chyba: Cosmos · bez nových prodejů"
    assert "Cosmos: CHYBA – přihlas se – uv run python -m sales_tracker sync cosmos --login" in text


def test_jeden_krok_spadne_ostatni_dobehnou(env):
    def broken():
        raise RuntimeError("tajný detail, který nemá být v e-mailu")

    steps = [
        daily.Step("cosmos", "Cosmos", broken),
        daily.Step("gumroad", "Gumroad", env.step(sale("gumroad", "g1", 1000))),
    ]
    assert env.run(steps) == 1
    subject, text = env.last()
    assert "Cosmos: CHYBA – neočekávaná chyba (RuntimeError)" in text
    assert "tajný detail" not in text
    assert "1 nový prodej" in subject
    assert "Traceback" in env.log()


def test_chyba_kroku_posledni_radek_vystupu(env):
    def gumroad_step():
        print("Stahuji…")
        print("Chybí GUMROAD_ACCESS_TOKEN v .env.")
        return 1

    env.run([daily.Step("gumroad", "Gumroad", gumroad_step)])
    assert "Gumroad: CHYBA – Chybí GUMROAD_ACCESS_TOKEN v .env." in env.last()[1]


def test_stari_posledniho_uspechu(env):
    env.run([daily.Step("cosmos", "Cosmos", ok_step)])
    assert env.state()["last_success"]["cosmos"] == NOW.isoformat()

    def failing():
        print("Načtení prodejů z Cosmosu selhalo.")
        return 1

    env.run([daily.Step("cosmos", "Cosmos", failing)], now=NOW + timedelta(days=2))
    assert "(naposledy staženo 22. 11. 08:00)" in env.last()[1]
    env.run([daily.Step("cosmos", "Cosmos", failing)], now=NOW + timedelta(days=4))
    assert "(naposledy staženo před 4 dny)" in env.last()[1]
    assert env.state()["last_success"]["cosmos"] == NOW.isoformat()  # neúspěch stav nepřepíše


def test_fab_se_nehlida(env):
    env.run([daily.Step("fab", "Fab", ok_step)])
    assert "fab" not in env.state()["last_success"]


def test_dry_run_nic_neposle_ani_nezmeni(env, capsys):
    env.run([daily.Step("gumroad", "Gumroad", env.step(sale("gumroad", "g1", 1000)))], dry_run=True)
    assert env.sent == []
    assert not (env.tmp / "state.json").exists()
    out = capsys.readouterr().out
    assert "zkušební běh" in out and "Prodeje 22. 11.:" in out


def test_stare_logy_se_mazou(env):
    logs = env.tmp / "logs"
    logs.mkdir()
    (logs / "daily_2026-09-01.log").write_text("starý", encoding="utf-8")
    (logs / "daily_2026-10-01.log").write_text("novější", encoding="utf-8")
    env.run([daily.Step("gumroad", "Gumroad", ok_step)])
    assert not (logs / "daily_2026-09-01.log").exists()
    assert (logs / "daily_2026-10-01.log").exists()


def test_castky_cesky():
    assert daily.format_money(2250, "USD") == "22,50 USD"
    assert daily.format_money(123456, "EUR") == "1 234,56 EUR"
    assert daily.format_money(-500, "USD") == "-5,00 USD"


def test_html_escapuje():
    report = daily.Report("x", [daily.Section("A", ["<b>Chata & spol.</b>"])])
    assert "&lt;b&gt;Chata &amp; spol.&lt;/b&gt;" in report.html()


def test_cli_run_daily(monkeypatch):
    from sales_tracker import cli

    calls = []
    monkeypatch.setattr(cli, "run_daily", lambda dry_run=False: calls.append(dry_run) or 7)
    assert cli.main(["run", "daily"]) == 7
    assert cli.main(["run", "daily", "--dry-run"]) == 7
    assert calls == [False, True]


def test_fab_bez_souboru_neni_chyba(tmp_path, monkeypatch, capsys):
    from sales_tracker import cli

    monkeypatch.setattr(cli, "FAB_DIR", tmp_path / "fab")
    assert cli.run_import_fab_daily() == 0
    assert "přeskakuji" in capsys.readouterr().out
