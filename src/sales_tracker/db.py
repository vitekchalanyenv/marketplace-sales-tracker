"""Local SQLite storage. A sale is identified by (marketplace, external_id)."""

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from sales_tracker.models import Sale

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
    marketplace   TEXT    NOT NULL,
    external_id   TEXT    NOT NULL,
    product_title TEXT,
    product_ref   TEXT,
    sold_at       TEXT    NOT NULL,  -- UTC, ISO 8601 with Z
    gross_cents   INTEGER NOT NULL,
    net_cents     INTEGER,
    currency      TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    raw           TEXT    NOT NULL,  -- original record as JSON
    first_seen_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (marketplace, external_id)
);
"""

# Fields compared to decide whether a stored sale changed. `raw` is left out on purpose:
# marketplaces put volatile display text in it (Gumroad "timestamp": "about 2 months ago").
COMPARED = ("product_title", "product_ref", "sold_at", "gross_cents", "net_cents", "currency", "status")


@dataclass(frozen=True)
class UpsertResult:
    new: int
    updated: int


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def _row(sale: Sale) -> dict:
    return {
        "marketplace": sale.marketplace,
        "external_id": sale.external_id,
        "product_title": sale.product_title,
        "product_ref": sale.product_ref,
        "sold_at": sale.sold_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gross_cents": sale.gross_cents,
        "net_cents": sale.net_cents,
        "currency": sale.currency,
        "status": str(sale.status),
        "raw": json.dumps(sale.raw, ensure_ascii=False, sort_keys=True),
    }


def upsert_sales(conn: sqlite3.Connection, sales: Iterable[Sale]) -> UpsertResult:
    """Insert new sales, update changed ones, leave the rest. All in one transaction."""
    new = updated = 0
    with conn:
        for sale in sales:
            row = _row(sale)
            existing = conn.execute(
                f"SELECT {', '.join(COMPARED)} FROM sales WHERE marketplace = ? AND external_id = ?",
                (row["marketplace"], row["external_id"]),
            ).fetchone()
            if existing is None:
                cols = ", ".join(row)
                conn.execute(
                    f"INSERT INTO sales ({cols}) VALUES ({', '.join(':' + c for c in row)})", row
                )
                new += 1
            elif existing != tuple(row[c] for c in COMPARED):
                assignments = ", ".join(f"{c} = :{c}" for c in (*COMPARED, "raw"))
                conn.execute(
                    f"UPDATE sales SET {assignments}, "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                    "WHERE marketplace = :marketplace AND external_id = :external_id",
                    row,
                )
                updated += 1
    return UpsertResult(new=new, updated=updated)


def has_sales(conn: sqlite3.Connection, marketplace: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sales WHERE marketplace = ? LIMIT 1", (marketplace,)).fetchone()
        is not None
    )
