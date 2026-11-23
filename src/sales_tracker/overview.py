"""Overview calculations for the dashboard (spec M6), without Streamlit so they can be tested.

The same rules as the morning e-mail: excluded sales are left out, a refund either changes the
sale's status (Gumroad, Cosmos: not counted) or is a negative row (Fab: counted, subtracts), CZK at
the ČNB rate of the sale's local day. Amounts in different currencies are never added together;
a CZK total is shown only when every row in it has a rate.
"""

import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sales_tracker import daily, fx

RECENT = 20


@dataclass(frozen=True)
class Row:
    marketplace: str
    external_id: str
    title: str | None
    product_key: str | None
    quantity: int
    net_cents: int
    currency: str
    sold_at: datetime  # UTC
    czk: int | None  # haléře; None = no rate

    @property
    def day(self) -> date:
        return daily._local(self.sold_at).date()


@dataclass
class Total:
    units: int = 0
    by_currency: dict[str, int] = field(default_factory=dict)
    czk: int = 0
    czk_missing: int = 0  # rows without a rate: the CZK total is then incomplete

    def add(self, row: Row) -> None:
        self.units += row.quantity
        self.by_currency[row.currency] = self.by_currency.get(row.currency, 0) + row.net_cents
        if row.czk is None:
            self.czk_missing += 1
        else:
            self.czk += row.czk

    @property
    def czk_complete(self) -> int | None:
        return self.czk if self.czk_missing == 0 else None


def total(rows: Iterable[Row]) -> Total:
    result = Total()
    for row in rows:
        result.add(row)
    return result


def load(conn: sqlite3.Connection, czk: Callable[[int, str, str], int | None] | None) -> list[Row]:
    """Every counted row, oldest first. czk: daily.CzkConverter (None = no CZK at all)."""
    rows = conn.execute(
        "SELECT marketplace, external_id, product_title, product_key, quantity, net_cents, currency, "
        "sold_at FROM sales WHERE (status = 'sold' OR quantity < 0) AND excluded = 0 "
        "ORDER BY sold_at, marketplace, external_id"
    ).fetchall()
    result = []
    for marketplace, external_id, title, key, quantity, net, currency, sold_at in rows:
        net = net or 0
        haler = net if currency == fx.HOME else (czk(net, currency, sold_at) if czk else None)
        result.append(Row(
            marketplace, external_id, title, key, quantity, net, currency,
            datetime.fromisoformat(sold_at), haler,
        ))
    return result


# --- periods and filters -----------------------------------------------------------------------

@dataclass(frozen=True)
class Period:
    label: str
    start: date | None  # inclusive, local; None = from the beginning
    end: date | None  # inclusive, local; None = until now


def _month_start(day: date, back: int = 0) -> date:
    index = day.year * 12 + day.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def fixed_periods(today: date) -> list[Period]:
    """The three numbers at the top: this month, last month, this year."""
    this_month = _month_start(today)
    return [
        Period("Tento měsíc", this_month, today),
        Period("Minulý měsíc", _month_start(today, 1), this_month - timedelta(days=1)),
        Period("Letos", date(today.year, 1, 1), today),
    ]


def filter_periods(today: date) -> list[Period]:
    """Choices of the period filter (the custom range is added by the page)."""
    this_month, last_month, this_year = fixed_periods(today)
    return [
        this_month, last_month, this_year,
        Period("Posledních 12 měsíců", _month_start(today, 11), today),
        Period("Vše", None, None),
    ]


def select(rows: Iterable[Row], period: Period, marketplaces: Iterable[str] | None = None) -> list[Row]:
    chosen = None if marketplaces is None else set(marketplaces)
    return [
        row for row in rows
        if (period.start is None or row.day >= period.start)
        and (period.end is None or row.day <= period.end)
        and (chosen is None or row.marketplace in chosen)
    ]


# --- aggregations ------------------------------------------------------------------------------

def _sort_key(item: tuple[str, Total]) -> tuple:
    name, value = item
    return (-value.czk, -value.units, name)


def by_marketplace(rows: Iterable[Row]) -> list[tuple[str, Total]]:
    """Highest income (CZK) first, like the e-mail."""
    groups: dict[str, Total] = {}
    for row in rows:
        groups.setdefault(row.marketplace, Total()).add(row)
    return sorted(groups.items(), key=_sort_key)


def months_between(first: date, last: date) -> list[str]:
    months, current = [], _month_start(first)
    while current <= last:
        months.append(f"{current.year}-{current.month:02d}")
        current = _month_start(current + timedelta(days=32))
    return months


@dataclass(frozen=True)
class MonthBar:
    month: str  # "2026-11"
    marketplace: str
    czk: int  # haléře of the rows that have a rate
    incomplete: bool


def monthly(rows: list[Row]) -> list[MonthBar]:
    """CZK per month and marketplace for the chart; months without sales are there with 0."""
    if not rows:
        return []
    totals: dict[tuple[str, str], Total] = {}
    for row in rows:
        totals.setdefault((f"{row.day.year}-{row.day.month:02d}", row.marketplace), Total()).add(row)
    marketplaces = sorted({row.marketplace for row in rows})
    bars = []
    for month in months_between(rows[0].day, max(row.day for row in rows)):
        for marketplace in marketplaces:
            value = totals.get((month, marketplace), Total())
            bars.append(MonthBar(month, marketplace, value.czk, value.czk_missing > 0))
    return bars


@dataclass
class ProductLine:
    name: str
    matched: bool
    total: Total = field(default_factory=Total)
    units_by_marketplace: dict[str, int] = field(default_factory=dict)


def products(rows: Iterable[Row], product_name: Callable[[str], str]) -> list[ProductLine]:
    """One line per catalog product, across marketplaces. Unmatched sales get a line per
    (marketplace, title), so nothing disappears and it is clear what to add to the catalog."""
    lines: dict[tuple, ProductLine] = {}
    for row in rows:
        if row.product_key:
            key = ("p", row.product_key)
            name, matched = product_name(row.product_key), True
        else:
            title = row.title or "(bez názvu)"
            key = ("u", row.marketplace, title)
            name, matched = f"nespárováno: {title} ({daily._name(row.marketplace)})", False
        line = lines.setdefault(key, ProductLine(name, matched))
        line.total.add(row)
        line.units_by_marketplace[row.marketplace] = (
            line.units_by_marketplace.get(row.marketplace, 0) + row.quantity
        )
    return sorted(lines.values(), key=lambda line: (not line.matched, *_sort_key((line.name, line.total))))


def recent(rows: Iterable[Row], count: int = RECENT) -> list[Row]:
    return sorted(rows, key=lambda row: (row.sold_at, row.marketplace, row.external_id), reverse=True)[:count]


# --- sources ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceStatus:
    marketplace: str
    last_sale: datetime | None
    last_update: datetime | None  # last successful download (automatic) or last new record (manual)
    automatic: bool
    stale: bool


def sources(conn: sqlite3.Connection, state: dict, now: datetime) -> list[SourceStatus]:
    """Per marketplace: the newest sale in the database and when the data was last refreshed.
    Gumroad and Cosmos are downloaded by the daily agent (its state has the last success); Fab and
    CGTrader are imported by hand (the last time a record was added)."""
    stats = {
        marketplace: (last_sale, last_seen)
        for marketplace, last_sale, last_seen in conn.execute(
            "SELECT marketplace, MAX(sold_at), MAX(first_seen_at) FROM sales GROUP BY marketplace"
        )
    }
    result = []
    for marketplace in daily.MARKETPLACE_NAMES:
        last_sale, last_seen = stats.get(marketplace, (None, None))
        automatic = marketplace in daily.WATCHED
        update = state.get("last_success", {}).get(marketplace) if automatic else last_seen
        update_at = datetime.fromisoformat(update) if update else None
        if update_at is not None and update_at > now:  # the demo has a fixed "now" in the past
            update_at = now
        stale = automatic and (update_at is None or (now - update_at).days >= daily.STALE_DAYS)
        result.append(SourceStatus(
            marketplace, datetime.fromisoformat(last_sale) if last_sale else None, update_at,
            automatic, stale,
        ))
    return result


# --- formatting --------------------------------------------------------------------------------

def money(value: Total) -> str:
    """'45,90 USD + 12,00 EUR (≈ 1 323,15 Kč)'; currencies are never added up."""
    if not value.by_currency:
        return "0,00 Kč"
    parts = " + ".join(
        daily.format_money(cents, currency) for currency, cents in sorted(value.by_currency.items())
    )
    if set(value.by_currency) == {fx.HOME}:
        return parts
    return f"{parts} ({czk_text(value)})"


def czk_text(value: Total) -> str:
    if value.czk_missing:
        return "Kč nedostupné, chybí kurz"
    return "≈ " + daily.format_money(value.czk, "Kč")


def czk_rounded(value: Total) -> str:
    """Whole crowns for the big numbers at the top; the exact amount is right below them."""
    if value.czk_missing:
        return "Kč nedostupné"
    crowns = int((Decimal(value.czk) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return "≈ " + f"{crowns:,}".replace(",", " ") + " Kč"


def month_label(month: str) -> str:
    """'2026-01' → '1/2026'."""
    year, number = month.split("-")
    return f"{int(number)}/{year}"


def when(row: Row) -> str:
    """Local date, with the time only where the marketplace gives it (like the e-mail)."""
    local = daily._local(row.sold_at)
    clock = "" if row.marketplace in daily.DAY_ONLY else f" {local:%H:%M}"
    return f"{local.day}. {local.month}. {local.year}{clock}"
