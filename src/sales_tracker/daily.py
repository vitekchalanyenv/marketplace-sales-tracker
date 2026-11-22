"""Daily agent (spec M5): run every source, then e-mail a morning report, every day.

Steps are the existing commands (sync gumroad, sync cosmos, import fab). Each runs on its own, so
one failing source does not stop the others. "New since the last report" is measured against the
database state saved when the last report was actually sent, so sales fetched by hand in between
are reported too and a failed e-mail is repeated the next day. The report is a list of sections,
so more (wishlists, ...) can be added later.
"""

import html
import io
import json
import sqlite3
import traceback
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sales_tracker import db

WATCHED = ("gumroad", "cosmos")  # automatic sources; Fab is uploaded by hand
STALE_DAYS = 3
LOG_KEEP_DAYS = 60
COSMOS_LOGIN_HINT = "sync cosmos --login"
MAX_MESSAGE = 160
LOCAL_TZ = ZoneInfo("Europe/Prague")
MARKETPLACE_NAMES = {"gumroad": "Gumroad", "cosmos": "Cosmos", "fab": "Fab", "cgtrader": "CGTrader"}
MONTHS = (
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
)


@dataclass(frozen=True)
class Step:
    key: str  # marketplace key, used for the "last success" state
    name: str  # shown to Vítek
    run: Callable[[], int]


@dataclass(frozen=True)
class StepResult:
    step: Step
    ok: bool
    output: str
    error: str | None  # short, safe for the e-mail


@dataclass(frozen=True)
class Snapshot:
    max_rowid: int
    not_sold: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class Section:
    title: str
    lines: list[str]


@dataclass
class Report:
    subject: str
    sections: list[Section] = field(default_factory=list)

    def text(self) -> str:
        parts = []
        for section in self.sections:
            parts.append(section.title.upper())
            parts.extend(f"- {line}" for line in section.lines)
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    def html(self) -> str:
        parts = ['<div style="font-family:sans-serif;font-size:14px">']
        for section in self.sections:
            parts.append(f"<h3>{html.escape(section.title)}</h3><ul>")
            parts.extend(f"<li>{html.escape(line)}</li>" for line in section.lines)
            parts.append("</ul>")
        parts.append("</div>")
        return "".join(parts)


Send = Callable[[Report], None]


# --- steps -----------------------------------------------------------------------------------

def run_step(step: Step) -> StepResult:
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            code = step.run()
    except Exception as exc:  # noqa: BLE001 – one broken source must not stop the others
        buffer.write(traceback.format_exc())
        return StepResult(step, False, buffer.getvalue(), f"neočekávaná chyba ({type(exc).__name__})")
    output = buffer.getvalue()
    if code == 0:
        return StepResult(step, True, output, None)
    return StepResult(step, False, output, _error_message(output))


def _error_message(output: str) -> str:
    if COSMOS_LOGIN_HINT in output:
        return f"přihlas se – uv run python -m sales_tracker {COSMOS_LOGIN_HINT}"
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    message = lines[-1] if lines else "selhalo bez výpisu"
    return message if len(message) <= MAX_MESSAGE else message[: MAX_MESSAGE - 1] + "…"


# --- database queries --------------------------------------------------------------------------

def snapshot(conn: sqlite3.Connection) -> Snapshot:
    max_rowid = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM sales").fetchone()[0]
    rows = conn.execute("SELECT marketplace, external_id FROM sales WHERE status != 'sold'")
    return Snapshot(max_rowid, frozenset(tuple(row) for row in rows))


SALE_COLUMNS = "marketplace, product_title, quantity, net_cents, currency, sold_at"


def new_sales(conn: sqlite3.Connection, since: Snapshot) -> list[tuple]:
    return conn.execute(
        f"SELECT {SALE_COLUMNS} FROM sales WHERE rowid > ? AND status = 'sold' AND excluded = 0 "
        "ORDER BY sold_at",
        (since.max_rowid,),
    ).fetchall()


def new_refunds(conn: sqlite3.Connection, since: Snapshot) -> list[tuple]:
    rows = conn.execute(
        f"SELECT marketplace, external_id, {SALE_COLUMNS} FROM sales "
        "WHERE status != 'sold' AND excluded = 0 ORDER BY sold_at"
    ).fetchall()
    return [row[2:] for row in rows if (row[0], row[1]) not in since.not_sold]


def month_totals(conn: sqlite3.Connection, today: date) -> list[tuple[str, str, int, int]]:
    """(currency, marketplace, units, net cents) for the local month of `today`.

    Refunds: Fab stores them as separate negative rows (counted, so they subtract); Gumroad and
    Cosmos change the sale's status (not counted).
    """
    start = datetime(today.year, today.month, 1, tzinfo=LOCAL_TZ)
    end = datetime(today.year + today.month // 12, today.month % 12 + 1, 1, tzinfo=LOCAL_TZ)
    return conn.execute(
        "SELECT currency, marketplace, SUM(quantity), SUM(net_cents) FROM sales "
        "WHERE sold_at >= ? AND sold_at < ? AND (status = 'sold' OR quantity < 0) AND excluded = 0 "
        "GROUP BY currency, marketplace ORDER BY currency, marketplace",
        (_utc_text(start), _utc_text(end)),
    ).fetchall()


def _utc_text(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- formatting --------------------------------------------------------------------------------

def format_money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", " ") + f",{rest:02d} {currency}"


def _plural_sales(n: int) -> str:
    if n == 1:
        return "1 nový prodej"
    return f"{n} nové prodeje" if 2 <= n <= 4 else f"{n} nových prodejů"


def _plural_days(n: int) -> str:
    return "1 dnem" if n == 1 else f"{n} dny"


def _local(moment: datetime | str) -> datetime:
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    return moment.astimezone(LOCAL_TZ)


def _when(moment: datetime | str) -> str:
    local = _local(moment)
    return f"{local.day}. {local.month}. {local:%H:%M}"


def _name(marketplace: str) -> str:
    return MARKETPLACE_NAMES.get(marketplace, marketplace)


def _sale_line(row: tuple) -> str:
    marketplace, title, quantity, net, currency, sold_at = row
    return (
        f"{_name(marketplace)} – {title or '(bez názvu)'} – {quantity}× – "
        f"čistě {format_money(net, currency)} ({_when(sold_at)})"
    )


def _subject(day: date, sales: list[tuple], failed: list[StepResult]) -> str:
    parts = []
    if failed:
        parts.append("⚠ chyba: " + ", ".join(r.step.name for r in failed))
    if sales:
        units = sum(row[2] for row in sales)
        currencies = {row[4] for row in sales}
        text = _plural_sales(units)
        if len(currencies) == 1:
            text += f", čistě {format_money(sum(row[3] for row in sales), currencies.pop())}"
        parts.append(text)
    else:
        parts.append("bez nových prodejů")
    return f"Prodeje {day.day}. {day.month}.: " + " · ".join(parts)


def build_report(
    *,
    day: date,
    results: list[StepResult],
    sales: list[tuple],
    refunds: list[tuple],
    month: list[tuple[str, str, int, int]],
    state: dict,
    now: datetime,
) -> Report:
    failed = [r for r in results if not r.ok]
    report = Report(_subject(day, sales, failed))

    report.sections.append(Section(
        "Nové prodeje od minulého souhrnu",
        [_sale_line(row) for row in sales] or ["Žádné nové prodeje."],
    ))
    if refunds:
        report.sections.append(Section("Refundy", [_sale_line(row) for row in refunds]))

    month_lines = []
    totals: dict[str, int] = {}
    for currency, marketplace, units, net in month:
        month_lines.append(f"{_name(marketplace)}: {units} ks, čistě {format_money(net, currency)}")
        totals[currency] = totals.get(currency, 0) + net
    for currency, net in totals.items():
        month_lines.append(f"Celkem: čistě {format_money(net, currency)}")
    report.sections.append(Section(
        f"Tento měsíc ({MONTHS[day.month - 1]} {day.year})",
        month_lines or ["Zatím žádné prodeje."],
    ))

    status_lines = []
    for result in results:
        if result.ok:
            status_lines.append(f"{result.step.name}: ok")
            continue
        line = f"{result.step.name}: CHYBA – {result.error}"
        last = state["last_success"].get(result.step.key) if result.step.key in WATCHED else None
        if last is not None:
            days = (now - datetime.fromisoformat(last)).days
            if days >= STALE_DAYS:
                line += f" (naposledy staženo před {_plural_days(days)})"
            else:
                line += f" (naposledy staženo {_when(last)})"
        status_lines.append(line)
    report.sections.append(Section("Stav zdrojů", status_lines))
    return report


# --- state and log -----------------------------------------------------------------------------

def _load_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        state = {}
    state.setdefault("last_success", {})
    return state


def _reported(state: dict) -> Snapshot | None:
    saved = state.get("reported")
    if not isinstance(saved, dict):
        return None
    return Snapshot(int(saved["max_rowid"]), frozenset(tuple(k) for k in saved["not_sold"]))


def _save_reported(state: dict, snap: Snapshot) -> None:
    state["reported"] = {"max_rowid": snap.max_rowid, "not_sold": sorted(list(k) for k in snap.not_sold)}


def _prune_logs(log_dir: Path, today: date) -> None:
    cutoff = today - timedelta(days=LOG_KEEP_DAYS)
    for path in log_dir.glob("daily_*.log"):
        try:
            day = date.fromisoformat(path.stem.removeprefix("daily_"))
        except ValueError:
            continue
        if day < cutoff:
            path.unlink()


# --- the run -----------------------------------------------------------------------------------

def run_daily(
    steps: Sequence[Step],
    *,
    db_path: Path,
    state_path: Path,
    log_dir: Path,
    send: Send | None,
    now: datetime,
) -> int:
    """Run all steps and send the report. send=None is a dry run: print only, change no state."""
    state = _load_state(state_path)
    conn = db.connect(db_path)
    try:
        since = _reported(state) or snapshot(conn)  # first run: do not report the whole history
    finally:
        conn.close()

    results = [run_step(step) for step in steps]
    day = _local(now).date()

    conn = db.connect(db_path)
    try:
        sales = new_sales(conn, since)
        refunds = new_refunds(conn, since)
        month = month_totals(conn, day)
        after = snapshot(conn)
    finally:
        conn.close()

    report = build_report(
        day=day, results=results, sales=sales, refunds=refunds, month=month, state=state, now=now,
    )

    log = [f"=== {now.isoformat()} ==="]
    for result in results:
        log.append(f"--- {result.step.name}: {'ok' if result.ok else 'CHYBA'} ---")
        log.append(result.output.rstrip())
    log.append(f"--- souhrn: {report.subject} ---")
    log.append(report.text().rstrip())

    sent = False
    if send is None:
        log.append("(zkušební běh, e-mail se neposlal)")
    else:
        try:
            send(report)
            sent = True
            log.append("e-mail odeslán")
        except Exception as exc:  # noqa: BLE001 – the log is the fallback; next report repeats
            log.append(f"E-MAIL SE NEPOSLAL: {exc}")

    if send is not None:
        for result in results:
            if result.ok and result.step.key in WATCHED:
                state["last_success"][result.step.key] = now.isoformat()
        if sent:
            _save_reported(state, after)
        elif "reported" not in state:
            _save_reported(state, since)  # anchor the first baseline, or the next run would skip these sales
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"daily_{day.isoformat()}.log").open("a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    _prune_logs(log_dir, day)

    print("\n".join(log))
    failed = any(not r.ok for r in results)
    return 1 if failed or (send is not None and not sent) else 0
