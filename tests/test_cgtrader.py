"""Import reportu z CGTraderu (spec M4b) na vymyšleném vzorku data/sample/cgtrader_report.csv."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_tracker import cgtrader, cli, db

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"
HEADER = ",".join(cgtrader.COLUMNS)
ROW = (
    "10000001,2026-01-04,https://www.cgtrader.com/3d-models/x/y/sample-medieval-village,9000001,"
    "https://www.cgtrader.com/designers/someone,Testland,$29.99,$12.00,0.65,11.35,55%,6.24"
)


def write(path: Path, *lines):
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")
    return path


def test_vzorek():
    report = cgtrader.parse_report(SAMPLE / "cgtrader_report.csv")
    assert report.skipped == []
    first, second, third = report.sales
    assert first.external_id == "10000001"
    assert first.product_ref == "9000001"
    assert first.product_title == "sample medieval village"
    assert first.sold_at == datetime(2026, 1, 3, 23, 0, tzinfo=UTC)  # 4. 1. 0:00 v Praze
    assert (first.gross_cents, first.net_cents, first.currency) == (1200, 624, "USD")
    assert isinstance(first.gross_cents, int) and first.quantity == 1 and first.status == "sold"
    assert second.raw["Transaction ID"] == "TX-SAMPLE-2"
    assert third.net_cents == 1614


def test_raw_bez_kupujiciho_a_zeme():
    for sale in cgtrader.parse_report(SAMPLE / "cgtrader_report.csv").sales:
        assert "Buyer" not in sale.raw and "Country" not in sale.raw
        assert "sample-buyer" not in str(sale.raw)


def test_chybejici_transaction_id_na_konci(tmp_path):
    report = cgtrader.parse_report(write(tmp_path / "r.csv", HEADER, ROW))
    assert report.skipped == []
    assert report.sales[0].raw["Transaction ID"] == ""


@pytest.mark.parametrize(("change", "reason"), [
    (lambda r: r.replace("10000001,", ",", 1), "OID"),
    (lambda r: r.replace("2026-01-04", "4.1.2026"), "Purchased"),
    (lambda r: r.replace("$12.00", "€12"), "Sold For"),
    (lambda r: r.replace(",6.24", ",-6.24"), "Final Earnings"),
    (lambda r: r.replace(",6.24", ",16.24"), "vyšší"),
    (lambda r: r + ",x,y", "sloupců"),
])
def test_vadny_radek_se_preskoci(tmp_path, change, reason):
    report = cgtrader.parse_report(write(tmp_path / "r.csv", HEADER, change(ROW)))
    assert report.sales == []
    assert report.skipped[0].line == 2 and reason in report.skipped[0].reason


def test_stejne_oid_dvakrat(tmp_path):
    report = cgtrader.parse_report(write(tmp_path / "r.csv", HEADER, ROW, ROW))
    assert report.sales == [] and len(report.skipped) == 2


def test_spatna_hlavicka(tmp_path):
    with pytest.raises(cgtrader.CgtraderFormatError, match="hlavička"):
        cgtrader.parse_report(write(tmp_path / "r.csv", HEADER.replace("OID", "Order"), ROW))


def test_bom_z_excelu(tmp_path):
    path = tmp_path / "r.csv"
    path.write_bytes(("﻿" + HEADER + "\r\n" + ROW + "\r\n").encode("utf-8"))
    assert len(cgtrader.parse_report(path).sales) == 1


# --- příkaz import cgtrader ---------------------------------------------------------------------

def run(tmp_path, *paths):
    catalog = tmp_path / "katalog.yaml"
    shutil.copy(SAMPLE / "katalog.yaml", catalog)
    return cli.import_cgtrader(list(paths), tmp_path / "sales.db", catalog_path=catalog)


def test_import_parovani_a_opakovani(tmp_path, capsys):
    sample = SAMPLE / "cgtrader_report.csv"
    assert run(tmp_path, sample) == 0
    out = capsys.readouterr().out
    assert "CGTrader (cgtrader_report.csv): řádků 3, nových 3, aktualizovaných 0, přeskočeno 0." in out
    assert "spárováno 3, nespárováno 0" in out  # ref i název ze slugu

    copy = shutil.copy(sample, tmp_path / "2026-01.csv")  # stejný report pod jiným jménem
    assert run(tmp_path, Path(copy)) == 0
    assert "nových 0, aktualizovaných 0" in capsys.readouterr().out
    conn = db.connect(tmp_path / "sales.db")
    keys = conn.execute("SELECT product_key FROM sales WHERE marketplace='cgtrader'").fetchall()
    assert sorted(k[0] for k in keys) == ["medieval-village", "medieval-village", "scifi-hangar"]


def test_bez_souboru(tmp_path, capsys):
    assert run(tmp_path) == 1
    assert "Žádný report z CGTraderu" in capsys.readouterr().out


def test_main_import_cgtrader(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "import_cgtrader", lambda paths, *a, **k: calls.append(paths) or 0)
    monkeypatch.setattr(cli, "CGTRADER_DIR", tmp_path)
    write(tmp_path / "b.csv", HEADER)
    write(tmp_path / "a.csv", HEADER)
    assert cli.main(["import", "cgtrader"]) == 0
    assert calls == [[tmp_path / "a.csv", tmp_path / "b.csv"]]


def test_denni_krok_bez_souboru_neni_chyba(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "CGTRADER_DIR", tmp_path / "cgtrader")
    assert cli.run_import_cgtrader_daily() == 0


def test_report_stazeni_se_preskoci(tmp_path, capsys):
    downloads = write(
        tmp_path / "item_downloads_report.csv",
        ",".join(cgtrader.DOWNLOADS_COLUMNS),
        "9000001,https://www.cgtrader.com/3d-models/x/y/sample,$29.99,"
        "https://www.cgtrader.com/designers/someone,2026-01-04,sample.zip",
    )
    assert cgtrader.is_downloads_report(downloads)
    assert not cgtrader.is_downloads_report(SAMPLE / "cgtrader_report.csv")
    assert run(tmp_path, downloads, SAMPLE / "cgtrader_report.csv") == 0
    out = capsys.readouterr().out
    assert "report stažení" in out and "nových 3" in out
    assert run(tmp_path, downloads) == 0
