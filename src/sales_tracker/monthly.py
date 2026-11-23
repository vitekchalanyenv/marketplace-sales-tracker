"""Monthly section of the first morning e-mail of a month (spec M5c). Numbers only, computed by the
same code as the dashboard (overview.py); no commentary from Claude (Vítek's decision)."""

import sqlite3
from collections.abc import Callable
from datetime import date

from sales_tracker import daily, overview


def last_month(today: date) -> overview.Period:
    return overview.fixed_periods(today)[1]


def key(today: date) -> str:
    """'2026-10' for any day in November 2026: the month the section is about."""
    start = last_month(today).start
    return f"{start.year}-{start.month:02d}"


def _month_title(period: overview.Period) -> str:
    return f"{daily.MONTHS[period.start.month - 1]} {period.start.year}"


def _sum_line(label: str, value: overview.Total) -> str:
    if not value.by_currency:
        return f"{label}: 0 ks, žádné prodeje"
    return f"{label}: {value.units} ks, čistě {overview.money(value)}"


def section(
    conn: sqlite3.Connection, czk, today: date, product_name: Callable[[str], str]
) -> daily.Section:
    rows = overview.load(conn, czk)
    month = last_month(today)
    before = last_month(month.start)
    year = overview.Period("rok", date(month.start.year, 1, 1), month.end)

    this = overview.select(rows, month)
    value = overview.total(this)
    lines = [_sum_line("Celkem", value)]
    for marketplace, item in overview.by_marketplace(this):
        lines.append(_sum_line(daily._name(marketplace), item))
    products = [line for line in overview.products(this, product_name) if line.matched]
    if products:
        best = products[0]
        lines.append(f"Nejlepší produkt: {best.name} ({best.total.units} ks, {overview.czk_text(best.total)})")

    previous = overview.total(overview.select(rows, before))
    change = ""
    if value.czk_complete is not None and previous.czk_complete:  # not None and not 0
        percent = round((value.czk_complete - previous.czk_complete) * 100 / previous.czk_complete)
        change = f" (změna {percent:+d} %)"
    title_before = _month_title(before)
    lines.append(
        f"{title_before[0].upper()}{title_before[1:]}: {previous.units} ks, {overview.czk_text(previous)}{change}"
    )

    year_label = f"Rok {month.start.year} celkem" if month.start.month == 12 else "Letos celkem"
    lines.append(_sum_line(year_label, overview.total(overview.select(rows, year))))
    return daily.Section(f"Minulý měsíc ({_month_title(month)})", lines)
