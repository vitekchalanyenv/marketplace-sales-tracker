"""How far the hand-uploaded sources reach (spec M5c): Fab and CGTrader are not downloaded by the
agent, so the morning e-mail says until when their data goes and warns when a report is missing."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sales_tracker import cgtrader, daily

FAB_STALE_DAYS = 7  # Vítek's decision 2026-11-23
CGTRADER_DUE_DAY = 10  # after this day of the month, last month's report should be there
FAB_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_fab_daily_sales_report", re.IGNORECASE)
MONTHS_GENITIVE = (
    "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince",
)


@dataclass(frozen=True)
class ManualStatus:
    key: str  # marketplace
    text: str  # the status line, without the marketplace name
    warning: bool
    in_subject: bool  # the warning is also in the e-mail subject


def fab_until(folder: Path, conn: sqlite3.Connection) -> tuple[date | None, bool]:
    """(last day covered, from the file name?). Fab names its report '<from>_<to>_fab_daily_sales_report.csv';
    a file named otherwise falls back to the newest Fab sale in the database."""
    ends = []
    for path in Path(folder).glob("*.csv") if Path(folder).is_dir() else []:
        match = FAB_NAME_RE.match(path.name)
        if match:
            try:
                ends.append(date.fromisoformat(match.group(2)))
            except ValueError:
                continue
    if ends:
        return max(ends), True
    newest = conn.execute("SELECT MAX(sold_at) FROM sales WHERE marketplace = 'fab'").fetchone()[0]
    return (daily._local(newest).date() if newest else None), False


def cgtrader_until(folder: Path) -> tuple[int, int] | None:
    """(year, month) of the newest sale in the sales reports; a downloads report does not count."""
    newest = None
    for path in Path(folder).glob("*.csv") if Path(folder).is_dir() else []:
        if cgtrader.is_downloads_report(path):
            continue
        try:
            report = cgtrader.parse_report(path)
        except cgtrader.CgtraderFormatError:
            continue
        for sale in report.sales:
            day = daily._local(sale.sold_at).date()
            month = (day.year, day.month)
            newest = month if newest is None or month > newest else newest
    return newest


def _month_name(year: int, month: int) -> str:
    return f"{daily.MONTHS[month - 1]} {year}"


def fab_status(until: date | None, from_name: bool, today: date) -> ManualStatus:
    if until is None:
        return ManualStatus("fab", "⚠ žádný report, ulož CSV do data/private/fab/", True, True)
    shown = f"{until.day}. {until.month}." + (f" {until.year}" if until.year != today.year else "")
    note = "" if from_name else " (podle posledního prodeje)"
    days = (today - until).days
    if days >= FAB_STALE_DAYS:
        return ManualStatus(
            "fab", f"⚠ data jen do {shown}{note} ({days} dní), stáhni nový report", True, True
        )
    return ManualStatus("fab", f"ok – data do {shown}{note}", False, False)


def cgtrader_status(until: tuple[int, int] | None, today: date) -> ManualStatus:
    last_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    due = today.day > CGTRADER_DUE_DAY
    if until is None:
        return ManualStatus("cgtrader", "⚠ žádný report prodejů", due, False)
    if until < last_month and due:
        return ManualStatus("cgtrader", f"⚠ chybí report za {_month_name(*last_month)}", True, False)
    return ManualStatus("cgtrader", f"ok – reporty do {MONTHS_GENITIVE[until[1] - 1]} {until[0]}", False, False)


def statuses(conn: sqlite3.Connection, today: date, fab_dir: Path, cgtrader_dir: Path) -> list[ManualStatus]:
    return [
        fab_status(*fab_until(fab_dir, conn), today),
        cgtrader_status(cgtrader_until(cgtrader_dir), today),
    ]
