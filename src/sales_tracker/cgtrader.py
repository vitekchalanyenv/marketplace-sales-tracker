"""CGTrader: import of the sales report CSV sent by e-mail (spec M4b, format in docs/ZDROJE.md).

One row = one sale (OID). The seller's earning rate varies, so the net amount is taken from
"Final Earnings" as reported. The buyer and their country are personal data and are not stored.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sales_tracker.fab import SkippedRow
from sales_tracker.models import Sale, Status

MARKETPLACE = "cgtrader"
COLUMNS = (
    "OID", "Purchased", "Product", "Product ID", "Buyer", "Country", "Original Price", "Sold For",
    "Payment Processing", "After tax", "Earning rate", "Final Earnings", "Transaction ID",
)
PERSONAL = ("Buyer", "Country")
CURRENCY = "USD"
# The report has dates only; read them as Vítek's local days, like Fab.
REPORT_TZ = ZoneInfo("Europe/Prague")

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONEY_RE = re.compile(r"^\$?\d+(\.\d{1,2})?$")


class CgtraderFormatError(Exception):
    """The file as a whole cannot be imported (not UTF-8, empty, unexpected header)."""


@dataclass
class CgtraderReport:
    sales: list[Sale] = field(default_factory=list)
    skipped: list[SkippedRow] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return len(self.sales) + len(self.skipped)


class _RowError(Exception):
    pass


def _cents(value: str, column: str) -> int:
    value = value.strip()
    if not MONEY_RE.match(value):
        raise _RowError(f"'{column}' není nezáporná částka v USD: {value!r}")
    return int(Decimal(value.removeprefix("$")) * 100)


def _title_from_url(url: str) -> str | None:
    slug = urlparse(url.strip()).path.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ") if slug else None


def _parse_row(values: dict[str, str]) -> Sale:
    oid = values["OID"].strip()
    if not oid:
        raise _RowError("prázdné 'OID'")
    day_text = values["Purchased"].strip()
    try:
        if not DAY_RE.match(day_text):
            raise ValueError
        day = date.fromisoformat(day_text)
    except ValueError:
        raise _RowError(f"'Purchased' není platné datum YYYY-MM-DD: {day_text!r}") from None

    gross = _cents(values["Sold For"], "Sold For")
    net = _cents(values["Final Earnings"], "Final Earnings")
    if net > gross:
        raise _RowError(f"'Final Earnings' ({net} ¢) je vyšší než 'Sold For' ({gross} ¢)")

    return Sale(
        marketplace=MARKETPLACE,
        external_id=oid,
        product_title=_title_from_url(values["Product"]),
        product_ref=values["Product ID"].strip() or None,
        sold_at=datetime.combine(day, time(0), tzinfo=REPORT_TZ).astimezone(UTC),
        gross_cents=gross,
        net_cents=net,
        currency=CURRENCY,
        status=Status.SOLD,
        raw={k: v for k, v in values.items() if k not in PERSONAL},
    )


def parse_report(path: Path) -> CgtraderReport:
    path = Path(path)
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CgtraderFormatError("soubor není v kódování UTF-8 (byl uložený v Excelu?)") from None

    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        raise CgtraderFormatError("soubor je prázdný")
    if tuple(h.strip() for h in header) != COLUMNS:
        raise CgtraderFormatError("neočekávaná hlavička, formát reportu se změnil")

    report = CgtraderReport()
    parsed: list[tuple[int, Sale]] = []
    for row in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) == len(COLUMNS) - 1:  # empty trailing Transaction ID is left out entirely
            row = [*row, ""]
        if len(row) != len(COLUMNS):
            report.skipped.append(SkippedRow(line, f"počet sloupců je {len(row)}, má být {len(COLUMNS)}"))
            continue
        try:
            parsed.append((line, _parse_row(dict(zip(COLUMNS, row, strict=True)))))
        except _RowError as exc:
            report.skipped.append(SkippedRow(line, str(exc)))

    lines_by_oid: dict[str, list[int]] = {}
    for line, sale in parsed:
        lines_by_oid.setdefault(sale.external_id, []).append(line)
    for line, sale in parsed:
        others = lines_by_oid[sale.external_id]
        if len(others) > 1:
            report.skipped.append(SkippedRow(
                line, f"OID {sale.external_id} je v souboru víckrát (řádky {', '.join(map(str, others))})"
            ))
        else:
            report.sales.append(sale)
    report.skipped.sort(key=lambda s: s.line)
    return report
