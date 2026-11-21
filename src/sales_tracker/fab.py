"""Fab: import of the daily sales report CSV downloaded by hand (spec M3, format in docs/ZDROJE.md).

One report row = one record: day + source + listing + license + base price, possibly several units,
negative for refunds. Fab's fee is not in the report; the creator's share is applied here.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sales_tracker.models import Sale, Status

MARKETPLACE = "fab"
COLUMNS = (
    "Day", "Source", "Listing Title", "License", "Base Price",
    "Total VAT", "Total Tax", "Net Units", "Net Sales",
)
CURRENCY = "USD"
# Creator's share of Net Sales, confirmed by Vítek 2026-11-21 (not in the report itself).
FAB_CREATOR_SHARE = Decimal("0.88")
# Report days are in Vítek's local time (decision 2026-11-21).
REPORT_TZ = ZoneInfo("Europe/Prague")

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONEY_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")
UNITS_RE = re.compile(r"^-?\d+$")


class FabFormatError(Exception):
    """The file as a whole cannot be imported (missing, not UTF-8, unexpected header)."""


@dataclass(frozen=True)
class SkippedRow:
    line: int
    reason: str


@dataclass
class FabReport:
    sales: list[Sale] = field(default_factory=list)
    skipped: list[SkippedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return len(self.sales) + len(self.skipped)


class _RowError(Exception):
    pass


def _cents(value: str, column: str) -> int:
    value = value.strip()
    if not MONEY_RE.match(value):
        raise _RowError(f"'{column}' není částka s max. 2 desetinnými místy: {value!r}")
    return int(Decimal(value) * 100)


def _text(value: str, column: str) -> str:
    value = value.strip()
    if not value:
        raise _RowError(f"prázdné '{column}'")
    return value


def _parse_row(values: dict[str, str], line: int, file_name: str) -> tuple[Sale, str | None]:
    day_text = values["Day"].strip()
    try:
        if not DAY_RE.match(day_text):
            raise ValueError
        day = date.fromisoformat(day_text)
    except ValueError:
        raise _RowError(f"'Day' není platné datum YYYY-MM-DD: {day_text!r}") from None

    source = _text(values["Source"], "Source")
    title = _text(values["Listing Title"], "Listing Title")
    license_ = _text(values["License"], "License")
    base = _cents(values["Base Price"], "Base Price")
    units_text = values["Net Units"].strip()
    if not UNITS_RE.match(units_text):
        raise _RowError(f"'Net Units' není celé číslo: {units_text!r}")
    units = int(units_text)
    gross = _cents(values["Net Sales"], "Net Sales")

    warning = None
    if base * units != gross:
        warning = (
            f"řádek {line}: Net Sales ({gross} ¢) ≠ Base Price × Net Units ({base} × {units}); "
            "uloženo podle Net Sales"
        )

    net = int((Decimal(gross) * FAB_CREATOR_SHARE).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    sold_at = datetime.combine(day, time(0), tzinfo=REPORT_TZ).astimezone(UTC)
    sale = Sale(
        marketplace=MARKETPLACE,
        external_id=f"{day.isoformat()}|{source}|{title}|{license_}|{base}",
        product_title=title,
        product_ref=None,
        sold_at=sold_at,
        gross_cents=gross,
        net_cents=net,
        currency=CURRENCY,
        status=Status.REFUNDED if units < 0 else Status.SOLD,
        raw={**values, "_file": file_name},
        quantity=units,
    )
    return sale, warning


def parse_report(path: Path) -> FabReport:
    path = Path(path)
    try:
        text = path.read_bytes().decode("utf-8-sig")  # Excel adds a BOM when saving
    except UnicodeDecodeError:
        raise FabFormatError("soubor není v kódování UTF-8 (byl uložený v Excelu?)") from None

    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        raise FabFormatError("soubor je prázdný")
    header = [h.strip() for h in header]
    if tuple(header) != COLUMNS:
        missing = [c for c in COLUMNS if c not in header]
        extra = [c for c in header if c not in COLUMNS]
        details = []
        if missing:
            details.append(f"chybí {', '.join(missing)}")
        if extra:
            details.append(f"navíc {', '.join(extra)}")
        if not details:
            details.append("jiné pořadí sloupců")
        raise FabFormatError(f"neočekávaná hlavička ({'; '.join(details)}), formát reportu se změnil")

    report = FabReport()
    parsed: list[tuple[int, Sale]] = []
    for row in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(COLUMNS):
            report.skipped.append(
                SkippedRow(line, f"počet sloupců je {len(row)}, má být {len(COLUMNS)}")
            )
            continue
        try:
            sale, warning = _parse_row(dict(zip(COLUMNS, row, strict=True)), line, path.name)
        except _RowError as exc:
            report.skipped.append(SkippedRow(line, str(exc)))
            continue
        parsed.append((line, sale))
        if warning:
            report.warnings.append(warning)

    lines_by_id: dict[str, list[int]] = {}
    for line, sale in parsed:
        lines_by_id.setdefault(sale.external_id, []).append(line)
    for line, sale in parsed:
        others = lines_by_id[sale.external_id]
        if len(others) > 1:
            report.skipped.append(SkippedRow(
                line,
                f"stejný den, listing, licence a cena je v souboru dvakrát (řádky {', '.join(map(str, others))})",
            ))
        else:
            report.sales.append(sale)
    report.skipped.sort(key=lambda s: s.line)
    return report
