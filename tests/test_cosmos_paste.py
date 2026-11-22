"""Ruční kopie tabulky prodejů z Cosmosu (spec M4a, cesta 2), vymyšlený vzorek data/sample/cosmos_paste.txt."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_tracker import cli, cosmos, db
from sales_tracker.catalog import CatalogError, load_catalog

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"
PRICES = {"sample-medieval-village": 1990, "sample-scifi-hangar": 990}


def paste(*lines):
    return "\r\n".join(lines) + "\r\n"


def parse(text, prices=PRICES):
    return cosmos.from_paste(text, prices.get)


def sample_text():
    return (SAMPLE / "cosmos_paste.txt").read_text(encoding="utf-8")


def test_vzorek():
    txs, skipped = parse(sample_text())
    assert skipped == []
    assert [tx.id for tx in txs] == ["30005", "30004", "30003", "30002", "30001"]
    first = txs[0]
    assert first.created_at == datetime(2026, 1, 20, 22, 30, tzinfo=UTC)  # 23:30 v Praze, zimní čas
    assert (first.amount_cents, first.payout_cents, first.virtual, first.refunded) == (1990, 1741, False, False)
    assert first.source == "paste"
    assert first.items[0].sku == "sample-medieval-village"
    assert first.items[0].title == "Medieval Village Environment"
    assert first.items[0].quantity == 1
    assert txs[3].created_at == datetime(2025, 7, 1, 6, 15, tzinfo=UTC)  # letní čas


def test_vic_produktu_podle_ceniku():
    tx = parse(sample_text())[0][1]
    assert [i.amount_cents for i in tx.items] == [1669, 831]  # 25,00 USD v poměru 19,90 : 9,90
    sales = cosmos.to_sales(tx)
    assert [s.net_cents for s in sales] == [1461, 727]
    assert sum(s.net_cents for s in sales) == 2188


def test_virtual_credits():
    tx = parse(sample_text())[0][2]
    assert tx.virtual and tx.payout_cents is None and tx.amount_cents == 990
    assert cosmos.to_sales(tx)[0].net_cents == 990


def test_raw_bez_zahlavi_stranky():
    for tx in parse(sample_text())[0]:
        assert "seller@example.org" not in str(tx.raw) and "Sample Seller" not in str(tx.raw)
        assert set(tx.raw) == {"id", "products", "amount", "payout", "date"}


def test_chybi_cena_pro_vic_produktu():
    txs, skipped = parse(sample_text(), {"sample-medieval-village": 1990})
    assert "30004" not in [tx.id for tx in txs]
    assert skipped[0].tx_id == "30004" and "sample-scifi-hangar" in skipped[0].reason
    assert len(txs) == 4  # jednoproduktové transakce cenu nepotřebují


@pytest.mark.parametrize(("block", "reason"), [
    (["#40001\t", "Produkt", "10.00 USD\t9.00 USD\t2026-01-01 10:00"], "sku"),
    (["#40001\t", "Produkt", "sku-a", "10.00 EUR\t9.00 EUR\t2026-01-01 10:00"], "USD"),
    (["#40001\t", "Produkt", "sku-a", "10.00\t9.00 USD\t2026-01-01 10:00"], "měna"),
    (["#40001\t", "Produkt", "sku-a", "10.005 USD\t9.00 USD\t2026-01-01 10:00"], "zlomek"),
    (["#40001\t", "Produkt", "sku-a", "10.00 USD\t9.00 USD\t2026-13-01 10:00"], "datum"),
    (["#40001\t", "Produkt", "sku-a", "Produkt", "sku-a", "10.00 USD\t9.00 USD\t2026-01-01 10:00"], "dvakrát"),
    (["#40001\t", "Produkt", "sku-a", "#40002\t"], "neúplná"),
])
def test_vadny_blok(block, reason):
    txs, skipped = parse(paste(*block))
    assert skipped and skipped[0].tx_id == "40001" and reason in skipped[0].reason
    assert "40001" not in [tx.id for tx in txs]


def test_stejna_transakce_vlozena_dvakrat():
    block = ["#40001\t", "Produkt", "sku-a", "10.00 USD\t9.00 USD\t2026-01-01 10:00"]
    txs, skipped = parse(paste(*block, *block))
    assert [tx.id for tx in txs] == ["40001"] and skipped == []


def test_bez_tabulky():
    assert parse(paste("Dashboard", "Settings")) == ([], [])


# --- katalog: price ---------------------------------------------------------------------------

def write_catalog(tmp_path, listing):
    path = tmp_path / "k.yaml"
    path.write_text(
        "products:\n  - key: a\n    name: A\n    listings:\n      cosmos:\n" + listing, encoding="utf-8"
    )
    return path


def test_katalog_cena():
    catalog = load_catalog(SAMPLE / "katalog.yaml")
    assert catalog.price("cosmos", "sample-medieval-village") == 1990
    assert catalog.price("cosmos", "sample-scifi-hangar") == 990
    assert catalog.price("cosmos", "neznamy") is None


@pytest.mark.parametrize("value", ["-1", "0", "9.999", "abc", "true"])
def test_katalog_spatna_cena(tmp_path, value):
    with pytest.raises(CatalogError, match="price"):
        load_catalog(write_catalog(tmp_path, f"        - ref: x\n          price: {value}\n"))


def test_katalog_cena_jen_s_ref(tmp_path):
    with pytest.raises(CatalogError, match="jen k listingu s 'ref'"):
        load_catalog(write_catalog(tmp_path, "        - title: X\n          price: 9.90\n"))


# --- příkaz import cosmos ---------------------------------------------------------------------

def run(tmp_path, *paths):
    catalog = tmp_path / "katalog.yaml"
    shutil.copy(SAMPLE / "katalog.yaml", catalog)
    return cli.import_cosmos(list(paths), tmp_path / "sales.db", catalog_path=catalog)


def test_import_a_opakovani(tmp_path, capsys):
    assert run(tmp_path, SAMPLE / "cosmos_paste.txt") == 0
    out = capsys.readouterr().out
    assert ("Cosmos (ruční kopie, cosmos_paste.txt): transakcí 5, už v DB 0, záznamů 6, nových 6, "
            "aktualizovaných 0, přeskočeno 0.") in out
    assert "spárováno 6, nespárováno 0" in out
    assert run(tmp_path, SAMPLE / "cosmos_paste.txt") == 0
    assert "transakcí 5, už v DB 5, záznamů 0, nových 0" in capsys.readouterr().out


def test_neprepise_data_z_agenta(tmp_path, capsys):
    from_api = cosmos.to_sales(cosmos.from_api({
        "id": 30005, "type": "real", "raw_amount": "19.9000", "created_at": "2026-01-20T22:30:41.000Z",
        "payout": {"amount": "17.4100", "currency": "USD"}, "refund_details": {"reason": "x"},
        "items": [{"sku": "sample-medieval-village", "title": "Medieval Village Environment",
                   "amount": "19.9000", "quantity": 1, "license": "individual"}],
    }))
    conn = db.connect(tmp_path / "sales.db")
    db.upsert_sales(conn, from_api)
    conn.close()

    run(tmp_path, SAMPLE / "cosmos_paste.txt")
    assert "už v DB 1" in capsys.readouterr().out
    conn = db.connect(tmp_path / "sales.db")
    row = conn.execute(
        "SELECT sold_at, status FROM sales WHERE external_id = '30005|sample-medieval-village'"
    ).fetchone()
    assert row == ("2026-01-20T22:30:41Z", "refunded")  # sekundy i refund z API zůstaly


def test_bez_souboru(tmp_path, capsys):
    assert run(tmp_path) == 1
    assert "Žádná ruční kopie" in capsys.readouterr().out


def test_main_import_cosmos(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "import_cosmos", lambda paths, *a, **k: calls.append(paths) or 0)
    monkeypatch.setattr(cli, "COSMOS_DIR", tmp_path)
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "api.json").write_text("{}", encoding="utf-8")
    assert cli.main(["import", "cosmos"]) == 0
    assert calls == [[tmp_path / "a.txt", tmp_path / "b.txt"]]
