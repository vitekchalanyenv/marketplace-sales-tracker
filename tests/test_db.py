"""Ukládání do SQLite: idempotence a aktualizace změněných prodejů (zlaté pravidlo 3)."""

import dataclasses
import sqlite3

from sales_tracker import db
from sales_tracker.gumroad import parse_sale
from sales_tracker.models import Status


def count_rows(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]


def test_ulozeni_dvakrat_nevytvori_duplicity(tmp_path, all_records):
    conn = db.connect(tmp_path / "sales.db")
    sales = [parse_sale(r) for r in all_records]

    first = db.upsert_sales(conn, sales)
    second = db.upsert_sales(conn, sales)

    assert (first.new, first.updated) == (5, 0)
    assert (second.new, second.updated) == (0, 0)
    assert count_rows(conn) == 5


def test_zmena_stavu_prodej_aktualizuje(tmp_path, all_records):
    conn = db.connect(tmp_path / "sales.db")
    sale = parse_sale(all_records[0])
    db.upsert_sales(conn, [sale])

    refunded = dataclasses.replace(sale, status=Status.REFUNDED)
    result = db.upsert_sales(conn, [refunded])

    assert (result.new, result.updated) == (0, 1)
    assert count_rows(conn) == 1
    status = conn.execute("SELECT status FROM sales").fetchone()[0]
    assert status == "refunded"


def test_zmena_jen_v_raw_neni_aktualizace(tmp_path, all_records):
    """Gumroad posílá např. "timestamp": "about 2 months ago", který se mění sám od sebe."""
    conn = db.connect(tmp_path / "sales.db")
    record = all_records[0]
    db.upsert_sales(conn, [parse_sale(record)])

    record["timestamp"] = "about 3 months ago"
    result = db.upsert_sales(conn, [parse_sale(record)])

    assert (result.new, result.updated) == (0, 0)


def test_stejne_id_na_jinem_marketplace_je_jiny_prodej(tmp_path, all_records):
    conn = db.connect(tmp_path / "sales.db")
    sale = parse_sale(all_records[0])
    other = dataclasses.replace(sale, marketplace="fab")

    result = db.upsert_sales(conn, [sale, other])

    assert result.new == 2
    assert count_rows(conn) == 2


def test_cas_a_castky_v_db(tmp_path, all_records):
    conn = db.connect(tmp_path / "sales.db")
    db.upsert_sales(conn, [parse_sale(all_records[0])])

    row = conn.execute(
        "SELECT sold_at, gross_cents, net_cents, currency, typeof(gross_cents) FROM sales"
    ).fetchone()
    assert row == ("2026-01-21T12:15:00Z", 1499, 1226, "USD", "integer")


def test_raw_se_ulozi_jako_json(tmp_path, all_records):
    conn = db.connect(tmp_path / "sales.db")
    db.upsert_sales(conn, [parse_sale(all_records[0])])

    raw = conn.execute("SELECT json_extract(raw, '$.order_id') FROM sales").fetchone()[0]
    assert raw == 900001


def test_has_sales(tmp_path, all_records):
    conn = db.connect(tmp_path / "sales.db")
    assert db.has_sales(conn, "gumroad") is False
    db.upsert_sales(conn, [parse_sale(all_records[0])])
    assert db.has_sales(conn, "gumroad") is True
    assert db.has_sales(conn, "fab") is False


def test_connect_vytvori_slozku(tmp_path):
    path = tmp_path / "nova" / "slozka" / "sales.db"
    db.connect(path).close()
    assert path.exists()
