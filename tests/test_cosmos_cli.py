"""Příkaz `sync cosmos` s podvrženým načítáním stránek (bez prohlížeče a sítě)."""

import copy
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_tracker import cli, db
from sales_tracker.cosmos import FetchError, SessionExpired

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
NOW = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def pages():
    return {
        n: json.loads((SAMPLE_DIR / f"cosmos_api_page{n}.json").read_text(encoding="utf-8"))
        for n in (1, 2)
    }


def run(tmp_path, loader, catalog=True):
    catalog_path = tmp_path / "katalog.yaml"
    if catalog:
        shutil.copy(SAMPLE_DIR / "katalog.yaml", catalog_path)
    return cli.sync_cosmos(
        tmp_path / "sales.db", loader, now=NOW, sleep=lambda s: None, catalog_path=catalog_path
    )


def rows(tmp_path):
    conn = db.connect(tmp_path / "sales.db")
    return conn.execute(
        "SELECT external_id, gross_cents, net_cents, status, product_key FROM sales "
        "WHERE marketplace = 'cosmos' ORDER BY external_id"
    ).fetchall()


def test_sync_a_opakovani(tmp_path, pages, capsys):
    def loader(n):
        return copy.deepcopy(pages[n])

    assert run(tmp_path, loader) == 0
    out = capsys.readouterr().out
    assert "transakcí 5, záznamů 6, nových 6, aktualizovaných 0, přeskočeno 0" in out
    assert "spárováno 6, nespárováno 0" in out
    assert "20002" in out and "refund" in out  # upozornění na neověřený formát refundu

    assert run(tmp_path, loader) == 0
    assert "nových 0, aktualizovaných 0" in capsys.readouterr().out
    assert len(rows(tmp_path)) == 6
    assert ("20002|sample-medieval-village", 1400, 1218, "refunded", "medieval-village") in rows(tmp_path)


def test_vadna_transakce_se_vypise_ostatni_ulozi(tmp_path, pages, capsys):
    pages[1]["data"][0]["payout"] = None
    assert run(tmp_path, lambda n: copy.deepcopy(pages[n])) == 0
    out = capsys.readouterr().out
    assert "Přeskočeno: transakce 20005" in out and "přeskočeno 1" in out
    assert len(rows(tmp_path)) == 5


def test_vyprsene_prihlaseni_nic_neulozi(tmp_path, capsys):
    def loader(n):
        raise SessionExpired("stránka skončila na /login")

    assert run(tmp_path, loader) == 1
    out = capsys.readouterr().out
    assert "sync cosmos --login" in out
    assert rows(tmp_path) == []


def test_chyba_na_druhe_strance_nic_neulozi(tmp_path, pages, capsys):
    def loader(n):
        if n == 2:
            raise FetchError("neočekávaný tvar odpovědi")
        return copy.deepcopy(pages[n])

    assert run(tmp_path, loader) == 1
    assert "Nic se neuložilo" in capsys.readouterr().out
    assert rows(tmp_path) == []


def test_main_login_jen_pro_cosmos(capsys):
    with pytest.raises(SystemExit):
        cli.main(["sync", "gumroad", "--login"])
