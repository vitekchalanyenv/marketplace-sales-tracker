"""Příkaz `import fab`, quantity v DB a idempotence opakovaného importu (spec M3)."""

import shutil
import sqlite3
from pathlib import Path

from sales_tracker import cli, db
from sales_tracker.gumroad import parse_sale

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
HEADER = "Day,Source,Listing Title,License,Base Price,Total VAT,Total Tax,Net Units,Net Sales"


def run(tmp_path, *paths):
    return cli.import_fab(
        list(paths),
        tmp_path / "sales.db",
        catalog_path=tmp_path / "katalog.yaml",
    )


def rows(tmp_path):
    conn = db.connect(tmp_path / "sales.db")
    return conn.execute(
        "SELECT external_id, quantity, gross_cents, net_cents, status, product_key FROM sales "
        "WHERE marketplace = 'fab' ORDER BY external_id"
    ).fetchall()


def write(path: Path, *lines):
    # newline="" → přesně CRLF jako skutečný report (jinak Windows udělá z \r\n \r\r\n)
    path.write_text("\r\n".join([HEADER, *lines]) + "\r\n", encoding="utf-8", newline="")
    return path


def test_import_a_opakovany_import(tmp_path, capsys):
    shutil.copy(SAMPLE_DIR / "katalog.yaml", tmp_path / "katalog.yaml")
    report = SAMPLE_DIR / "fab_report.csv"

    assert run(tmp_path, report) == 0
    out = capsys.readouterr().out
    assert "řádků 6, nových 6, aktualizovaných 0, přeskočeno 0" in out
    assert "spárováno 5, nespárováno 1" in out
    assert "Brand New Sample Listing" in out

    assert run(tmp_path, report) == 0
    assert "nových 0, aktualizovaných 0" in capsys.readouterr().out
    assert len(rows(tmp_path)) == 6


def test_prekryvajici_se_reporty(tmp_path, capsys):
    a = write(tmp_path / "a.csv",
              "2026-01-01,Fab,X,Personal,1.0,0,0,1,1.0",
              "2026-01-02,Fab,X,Personal,1.0,0,0,1,1.0")
    b = write(tmp_path / "b.csv",
              "2026-01-02,Fab,X,Personal,1.0,0,0,1,1.0",
              "2026-01-03,Fab,X,Personal,1.0,0,0,1,1.0")
    run(tmp_path, a)
    run(tmp_path, b)
    out = capsys.readouterr().out
    assert "nových 1, aktualizovaných 0" in out
    assert len(rows(tmp_path)) == 3


def test_zmena_poctu_kusu_je_aktualizace(tmp_path, capsys):
    run(tmp_path, write(tmp_path / "a.csv", "2026-01-01,Fab,X,Personal,1.0,0,0,1,1.0"))
    run(tmp_path, write(tmp_path / "b.csv", "2026-01-01,Fab,X,Personal,1.0,0,0,2,2.0"))
    assert "nových 0, aktualizovaných 1" in capsys.readouterr().out
    assert rows(tmp_path)[0][1:4] == (2, 200, 176)


def test_vadny_radek_se_vypise(tmp_path, capsys):
    path = write(tmp_path / "a.csv",
                 "2026-01-01,Fab,X,Personal,1.0,0,0,1,1.0",
                 "2026-13-01,Fab,X,Personal,1.0,0,0,1,1.0")
    assert run(tmp_path, path) == 0
    out = capsys.readouterr().out
    assert "řádek 3" in out and "Day" in out and "přeskočeno 1" in out


def test_spatna_hlavicka_nic_neulozi(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("Day,Listing,Units\r\n2026-01-01,X,1\r\n", encoding="utf-8")
    assert run(tmp_path, path) == 1
    out = capsys.readouterr().out
    assert "bad.csv" in out and "Nic se z něj neuložilo" in out
    assert rows(tmp_path) == []


def test_vadny_soubor_nezastavi_ostatni(tmp_path, capsys):
    bad = tmp_path / "a_bad.csv"
    bad.write_text("nesmysl\r\n", encoding="utf-8")
    good = write(tmp_path / "b_good.csv", "2026-01-01,Fab,X,Personal,1.0,0,0,1,1.0")
    assert run(tmp_path, bad, good) == 1
    assert len(rows(tmp_path)) == 1


def test_bez_cesty_nacte_vsechna_csv_ze_slozky(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "fab"
    folder.mkdir()
    write(folder / "2026-01-01_2026-01-31.csv", "2026-01-05,Fab,X,Personal,1.0,0,0,1,1.0")
    write(folder / "2026-02-01_2026-02-28.csv", "2026-02-05,Fab,X,Personal,1.0,0,0,1,1.0")
    (folder / "poznamka.txt").write_text("ignorovat", encoding="utf-8")

    paths = cli.fab_report_paths(None, folder)
    assert [p.name for p in paths] == ["2026-01-01_2026-01-31.csv", "2026-02-01_2026-02-28.csv"]
    assert run(tmp_path, *paths) == 0
    assert len(rows(tmp_path)) == 2


def test_prazdna_slozka(tmp_path, capsys):
    (tmp_path / "fab").mkdir()
    assert cli.fab_report_paths(None, tmp_path / "fab") == []
    assert run(tmp_path) == 1
    assert "Žádný report" in capsys.readouterr().out


def test_neexistujici_soubor(tmp_path, capsys):
    assert run(tmp_path, tmp_path / "neni.csv") == 1
    assert "neni.csv" in capsys.readouterr().out


def test_main_import_fab_parsuje_argumenty(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "import_fab", lambda paths, *a, **k: calls.append(paths) or 0)
    monkeypatch.setattr(cli, "FAB_DIR", tmp_path)
    write(tmp_path / "x.csv", "2026-01-05,Fab,X,Personal,1.0,0,0,1,1.0")

    assert cli.main(["import", "fab"]) == 0
    assert cli.main(["import", "fab", str(tmp_path / "x.csv")]) == 0
    assert [[p.name for p in c] for c in calls] == [["x.csv"], ["x.csv"]]


# --- quantity v DB a u Gumroadu ----------------------------------------------------------------


def test_gumroad_quantity(all_records):
    record = all_records[0]
    assert parse_sale(record).quantity == 1
    record["quantity"] = 3
    assert parse_sale(record).quantity == 3
    del record["quantity"]
    assert parse_sale(record).quantity == 1


def test_stara_db_dostane_quantity_1(tmp_path):
    path = tmp_path / "sales.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE sales (
            marketplace TEXT NOT NULL, external_id TEXT NOT NULL, product_title TEXT,
            product_ref TEXT, sold_at TEXT NOT NULL, gross_cents INTEGER NOT NULL,
            net_cents INTEGER, currency TEXT NOT NULL, status TEXT NOT NULL, raw TEXT NOT NULL,
            product_key TEXT,
            first_seen_at TEXT NOT NULL DEFAULT 'x', updated_at TEXT NOT NULL DEFAULT 'x',
            PRIMARY KEY (marketplace, external_id)
        );
        INSERT INTO sales (marketplace, external_id, sold_at, gross_cents, currency, status, raw)
        VALUES ('gumroad', 'old', '2026-01-01T00:00:00Z', 100, 'USD', 'sold', '{}');
        """
    )
    old.close()
    conn = db.connect(path)
    assert conn.execute("SELECT quantity FROM sales").fetchone() == (1,)
