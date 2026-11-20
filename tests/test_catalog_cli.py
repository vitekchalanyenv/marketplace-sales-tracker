"""Párování prodejů v DB a příkazy `catalog check` / `catalog match` (spec M2)."""

import dataclasses
import shutil
import sqlite3
from datetime import date
from pathlib import Path

import httpx
import pytest

from sales_tracker import cli, db
from sales_tracker.gumroad import parse_sale

SAMPLE_CATALOG = Path(__file__).resolve().parent.parent / "data" / "sample" / "katalog.yaml"


@pytest.fixture
def paths(tmp_path):
    catalog = tmp_path / "katalog.yaml"
    shutil.copy(SAMPLE_CATALOG, catalog)
    return catalog, tmp_path / "sales.db"


@pytest.fixture
def filled_db(paths, all_records):
    """DB se 4 vymyšlenými prodeji: 3 z Gumroadu (známé produkty) a 1 z Fabu (neznámý listing)."""
    _, db_path = paths
    sales = [parse_sale(r) for r in all_records[:3]]
    fab = dataclasses.replace(
        sales[0], marketplace="fab", external_id="fab-1", product_ref=None,
        product_title="Brand New Listing",
    )
    conn = db.connect(db_path)
    db.upsert_sales(conn, [*sales, fab])
    conn.close()
    return db_path


def keys(db_path) -> dict[str, str | None]:
    conn = db.connect(db_path)
    return dict(conn.execute("SELECT external_id, product_key FROM sales"))


def test_match_priradi_produkty(paths, filled_db, capsys):
    catalog, db_path = paths
    assert cli.catalog_match(catalog, db_path) == 0

    assert keys(db_path) == {
        "SAMPLE-aaaaaaaaaaaaaaaaaaaa==": "medieval-village",
        "SAMPLE-bbbbbbbbbbbbbbbbbbbb==": "scifi-hangar",
        "SAMPLE-cccccccccccccccccccc==": "medieval-village",
        "fab-1": None,
    }
    out = capsys.readouterr().out
    assert "spárováno 3" in out and "nespárováno 1" in out
    assert "Brand New Listing" in out


def test_match_po_uprave_katalogu_prepocita(paths, filled_db):
    catalog, db_path = paths
    cli.catalog_match(catalog, db_path)

    text = catalog.read_text(encoding="utf-8")
    text = text.replace('      gumroad:\n        - ref: "SAMPLE-prod-scifi-hangar=="\n', "")
    text = text.replace("      fab:\n        - title: \"Sci-Fi Hangar Environment\"",
                        "      fab:\n        - title: \"Brand New Listing\"")
    catalog.write_text(text, encoding="utf-8")
    cli.catalog_match(catalog, db_path)

    result = keys(db_path)
    assert result["SAMPLE-bbbbbbbbbbbbbbbbbbbb=="] is None  # listing z katalogu zmizel → zpět NULL
    assert result["fab-1"] == "scifi-hangar"


def test_check_vypise_nesparovane_s_navrhem_a_yaml(paths, filled_db, capsys):
    catalog, db_path = paths
    conn = db.connect(db_path)
    conn.execute("UPDATE sales SET product_title = 'Medieval Village Environment UE5' "
                 "WHERE external_id = 'fab-1'")
    conn.commit()
    conn.close()

    assert cli.catalog_check(catalog, db_path) == 0
    out = capsys.readouterr().out
    assert "Katalog je v pořádku (2 produkty)" in out
    assert "fab" in out and "Medieval Village Environment UE5" in out
    assert "medieval-village" in out  # návrh
    assert '- title: "Medieval Village Environment UE5"' in out  # úryvek YAML
    # úryvek jde vložit pod "listings:" beze změny odsazení (marketplace na 6 mezerách)
    assert '\n      fab:\n        - title: "Medieval Village Environment UE5"' in out
    assert "@" not in out


def test_check_seskupi_stejne_listingy(paths, filled_db, capsys):
    catalog, db_path = paths
    conn = db.connect(db_path)
    sale = parse_sale(
        {"id": "x2", "created_at": "2026-01-01T00:00:00Z", "price": 100, "product_name": "Unknown"}
    )
    db.upsert_sales(conn, [sale, dataclasses.replace(sale, external_id="x3")])
    conn.close()

    cli.catalog_check(catalog, db_path)
    out = capsys.readouterr().out
    assert out.count("Unknown") >= 1
    assert "2 prodeje" in out


def test_check_s_chybou_v_katalogu(paths, filled_db, capsys):
    catalog, db_path = paths
    catalog.write_text("products:\n  - key: Spatne\n", encoding="utf-8")
    assert cli.catalog_check(catalog, db_path) == 1
    out = capsys.readouterr().out
    assert "chyb" in out.lower()


def test_match_s_chybou_v_katalogu_nic_nezmeni(paths, filled_db):
    catalog, db_path = paths
    cli.catalog_match(catalog, db_path)
    before = keys(db_path)

    catalog.write_text("products: 5\n", encoding="utf-8")
    assert cli.catalog_match(catalog, db_path) == 1
    assert keys(db_path) == before


def test_chybejici_katalog(tmp_path, capsys):
    assert cli.catalog_check(tmp_path / "neni.yaml", tmp_path / "sales.db") == 1
    out = capsys.readouterr().out
    assert "data/sample/katalog.yaml" in out


def test_vse_sparovano(paths, all_records, capsys):
    catalog, db_path = paths
    conn = db.connect(db_path)
    db.upsert_sales(conn, [parse_sale(r) for r in all_records])
    conn.close()

    assert cli.catalog_match(catalog, db_path) == 0
    out = capsys.readouterr().out
    assert "spárováno 5" in out and "nespárováno 0" in out


# --- sync páruje automaticky ------------------------------------------------------------------


def serve(page1, page2):
    return httpx.MockTransport(
        lambda r: httpx.Response(200, json=page2 if "page_key" in r.url.params else page1)
    )


def test_sync_paruje(paths, page1, page2, capsys):
    catalog, db_path = paths
    code = cli.sync_gumroad(
        "t", db_path, transport=serve(page1, page2), sleep=lambda s: None,
        today=date(2026, 11, 20), catalog_path=catalog,
    )
    assert code == 0
    assert set(keys(db_path).values()) == {"medieval-village", "scifi-hangar"}
    assert "nespárováno 0" in capsys.readouterr().out


def test_sync_bez_katalogu_projde_s_upozornenim(tmp_path, page1, page2, capsys):
    code = cli.sync_gumroad(
        "t", tmp_path / "sales.db", transport=serve(page1, page2), sleep=lambda s: None,
        today=date(2026, 11, 20), catalog_path=tmp_path / "neni.yaml",
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "nových 5" in out
    assert "katalog" in out.lower()


def test_sync_s_vadnym_katalogem_ulozi_prodeje(paths, page1, page2, capsys):
    catalog, db_path = paths
    catalog.write_text("products: 5\n", encoding="utf-8")
    code = cli.sync_gumroad(
        "t", db_path, transport=serve(page1, page2), sleep=lambda s: None,
        today=date(2026, 11, 20), catalog_path=catalog,
    )
    assert code == 0
    assert len(keys(db_path)) == 5
    assert "catalog check" in capsys.readouterr().out


# --- migrace DB z M1 ---------------------------------------------------------------------------


def test_stara_db_z_m1_dostane_sloupec_product_key(tmp_path, all_records):
    path = tmp_path / "sales.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE sales (
            marketplace TEXT NOT NULL, external_id TEXT NOT NULL, product_title TEXT,
            product_ref TEXT, sold_at TEXT NOT NULL, gross_cents INTEGER NOT NULL,
            net_cents INTEGER, currency TEXT NOT NULL, status TEXT NOT NULL, raw TEXT NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT 'x', updated_at TEXT NOT NULL DEFAULT 'x',
            PRIMARY KEY (marketplace, external_id)
        );
        INSERT INTO sales (marketplace, external_id, sold_at, gross_cents, currency, status, raw)
        VALUES ('gumroad', 'old', '2026-01-01T00:00:00Z', 100, 'USD', 'sold', '{}');
        """
    )
    old.close()

    conn = db.connect(path)
    assert conn.execute("SELECT product_key FROM sales").fetchone() == (None,)
    db.connect(path).close()  # druhé připojení migraci nezopakuje ani nespadne
