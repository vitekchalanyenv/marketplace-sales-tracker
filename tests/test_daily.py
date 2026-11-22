"""Denní agent (spec M5): kroky jsou podvržené funkce, notifikace se jen zaznamenají."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from sales_tracker import daily, db
from sales_tracker.models import Sale, Status

NOW = datetime(2026, 11, 22, 7, 0, tzinfo=UTC)


def sale(marketplace, external_id, net, *, quantity=1, status=Status.SOLD, currency="USD"):
    return Sale(
        marketplace=marketplace, external_id=external_id, product_title="Vymyšlený produkt",
        product_ref=None, sold_at=NOW, gross_cents=net * 2, net_cents=net, currency=currency,
        status=status, raw={}, quantity=quantity,
    )


@pytest.fixture
def env(tmp_path):
    notes = []

    def run(steps, now=NOW):
        code = daily.run_daily(
            steps, db_path=tmp_path / "sales.db", state_path=tmp_path / "state.json",
            log_dir=tmp_path / "logs", notify=lambda title, lines: notes.append((title, lines)),
            now=now,
        )
        return code

    env = type("Env", (), {})()
    env.run, env.notes, env.tmp = run, notes, tmp_path
    env.db = tmp_path / "sales.db"
    return env


def store(env, *sales):
    """Krok, který jen uloží prodeje (jako sync)."""
    def step():
        conn = db.connect(env.db)
        try:
            db.upsert_sales(conn, sales)
        finally:
            conn.close()
        print("hotovo")
        return 0
    return step


def ok_step():
    print("nic nového")
    return 0


def test_vse_ok_bez_novych_bez_notifikace(env):
    steps = [daily.Step("gumroad", "Gumroad", ok_step), daily.Step("cosmos", "Cosmos", ok_step)]
    assert env.run(steps) == 0
    assert env.notes == []
    log = (env.tmp / "logs" / "daily_2026-11-22.log").read_text(encoding="utf-8")
    assert "Gumroad" in log and "nic nového" in log


def test_nove_prodeje_jedna_notifikace_se_souctem(env):
    steps = [
        daily.Step("gumroad", "Gumroad", store(env, sale("gumroad", "g1", 1000))),
        daily.Step("cosmos", "Cosmos", store(env, sale("cosmos", "c1", 1225), sale("cosmos", "c2", 25))),
    ]
    assert env.run(steps) == 0
    assert len(env.notes) == 1
    title, lines = env.notes[0]
    text = "\n".join([title, *lines])
    assert "3 nové prodeje, čistě 22,50 USD (Cosmos 2, Gumroad 1)" in text


def test_druhy_beh_uz_nic_nehlasi(env):
    step = store(env, sale("gumroad", "g1", 1000))
    env.run([daily.Step("gumroad", "Gumroad", step)])
    env.run([daily.Step("gumroad", "Gumroad", step)])
    assert len(env.notes) == 1


def test_mnozstvi_a_meny_zvlast(env):
    steps = [daily.Step("fab", "Fab", store(
        env, sale("fab", "f1", 500, quantity=2), sale("fab", "f2", 300, currency="EUR"),
    ))]
    env.run(steps)
    text = "\n".join(env.notes[0][1])
    assert "2 nové prodeje, čistě 5,00 USD (Fab 2)" in text
    assert "1 nový prodej, čistě 3,00 EUR (Fab 1)" in text


def test_refund_zmenou_existujiciho_prodeje(env):
    env.run([daily.Step("cosmos", "Cosmos", store(env, sale("cosmos", "c1", 1000)))])
    refunded = sale("cosmos", "c1", 1000, status=Status.REFUNDED)
    env.run([daily.Step("cosmos", "Cosmos", store(env, refunded))], now=NOW + timedelta(days=1))
    assert len(env.notes) == 2
    assert "1 refund" in "\n".join(env.notes[1][1])


def test_vyprsene_prihlaseni_cosmos(env):
    def cosmos_step():
        print("Přihlášení do Cosmosu vypršelo (x). Nic se neuložilo. Přihlas se: "
              "uv run python -m sales_tracker sync cosmos --login")
        return 1

    steps = [daily.Step("cosmos", "Cosmos", cosmos_step), daily.Step("gumroad", "Gumroad", ok_step)]
    assert env.run(steps) == 1
    title, lines = env.notes[0]
    assert "selhalo" in title
    assert any(line.startswith("Cosmos: přihlas se") and "sync cosmos --login" in line for line in lines)


def test_jeden_krok_spadne_ostatni_dobehnou(env):
    def broken():
        raise RuntimeError("tajný detail, který nemá být v notifikaci")

    steps = [
        daily.Step("cosmos", "Cosmos", broken),
        daily.Step("gumroad", "Gumroad", store(env, sale("gumroad", "g1", 1000))),
    ]
    assert env.run(steps) == 1
    text = "\n".join(env.notes[0][1])
    assert "Cosmos: neočekávaná chyba (RuntimeError)" in text
    assert "tajný detail" not in text
    assert "1 nový prodej" in text
    log = (env.tmp / "logs" / "daily_2026-11-22.log").read_text(encoding="utf-8")
    assert "Traceback" in log


def test_chyba_kroku_posledni_radek_vystupu(env):
    def gumroad_step():
        print("Stahuji…")
        print("Chybí GUMROAD_ACCESS_TOKEN v .env.")
        return 1

    env.run([daily.Step("gumroad", "Gumroad", gumroad_step)])
    assert "Gumroad: Chybí GUMROAD_ACCESS_TOKEN v .env." in env.notes[0][1]


def test_stari_posledniho_uspechu(env):
    env.run([daily.Step("cosmos", "Cosmos", ok_step)])
    state = json.loads((env.tmp / "state.json").read_text(encoding="utf-8"))
    assert state["last_success"]["cosmos"] == NOW.isoformat()

    def failing():
        print("Načtení prodejů z Cosmosu selhalo.")
        return 1

    env.run([daily.Step("cosmos", "Cosmos", failing)], now=NOW + timedelta(days=2))
    assert "naposledy" not in "\n".join(env.notes[-1][1])
    env.run([daily.Step("cosmos", "Cosmos", failing)], now=NOW + timedelta(days=4))
    assert "naposledy staženo před 4 dny" in "\n".join(env.notes[-1][1])
    # neúspěch stav nepřepíše
    state = json.loads((env.tmp / "state.json").read_text(encoding="utf-8"))
    assert state["last_success"]["cosmos"] == NOW.isoformat()


def test_fab_se_nehlida(env):
    env.run([daily.Step("fab", "Fab", ok_step)])
    state = json.loads((env.tmp / "state.json").read_text(encoding="utf-8"))
    assert "fab" not in state["last_success"]


def test_stare_logy_se_mazou(env):
    logs = env.tmp / "logs"
    logs.mkdir()
    (logs / "daily_2026-09-01.log").write_text("starý", encoding="utf-8")
    (logs / "daily_2026-10-01.log").write_text("novější", encoding="utf-8")
    env.run([daily.Step("gumroad", "Gumroad", ok_step)])
    assert not (logs / "daily_2026-09-01.log").exists()
    assert (logs / "daily_2026-10-01.log").exists()


def test_selhani_notifikace_neshodi_agenta(tmp_path):
    def notify(title, lines):
        raise OSError("toast nejde")

    steps = [daily.Step("gumroad", "Gumroad", lambda: 1)]
    code = daily.run_daily(
        steps, db_path=tmp_path / "sales.db", state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs", notify=notify, now=NOW,
    )
    assert code == 1
    assert "notifikace" in (tmp_path / "logs" / "daily_2026-11-22.log").read_text(encoding="utf-8")


def test_castky_cesky():
    assert daily.format_money(2250, "USD") == "22,50 USD"
    assert daily.format_money(123456, "EUR") == "1 234,56 EUR"
    assert daily.format_money(-500, "USD") == "-5,00 USD"


def test_cli_run_daily(monkeypatch):
    from sales_tracker import cli

    monkeypatch.setattr(cli, "run_daily", lambda: 7)
    assert cli.main(["run", "daily"]) == 7


def test_fab_bez_souboru_neni_chyba(tmp_path, monkeypatch, capsys):
    from sales_tracker import cli

    monkeypatch.setattr(cli, "FAB_DIR", tmp_path / "fab")
    assert cli.run_import_fab_daily() == 0
    assert "přeskakuji" in capsys.readouterr().out
