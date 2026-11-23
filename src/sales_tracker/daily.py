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

from sales_tracker import db, fx, weekly

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
    intro: str | None = None  # a paragraph above the list (the weekly commentary)
    intro_label: str | None = None


@dataclass
class Report:
    subject: str
    sections: list[Section] = field(default_factory=list)

    def text(self) -> str:
        parts = []
        for section in self.sections:
            parts.append(section.title.upper())
            if section.intro:
                parts.append(f"{section.intro_label}: {section.intro}" if section.intro_label else section.intro)
            parts.extend(f"- {line}" for line in section.lines)
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    def html(self) -> str:
        parts = ['<div style="font-family:sans-serif;font-size:14px">']
        for section in self.sections:
            parts.append(f"<h3>{html.escape(section.title)}</h3>")
            if section.intro:
                label = f"<b>{html.escape(section.intro_label)}:</b> " if section.intro_label else ""
                parts.append(
                    '<p style="font-style:italic;background:#f5f3ff;border-left:3px solid #8b5cf6;'
                    f'padding:8px 12px;margin:0 0 8px">{label}{html.escape(section.intro)}</p>'
                )
            parts.append("<ul>")
            parts.extend(f"<li>{html.escape(line)}</li>" for line in section.lines)
            parts.append("</ul>")
        parts.append("</div>")
        return "".join(parts)


Send = Callable[[Report], None]


@dataclass(frozen=True)
class WeeklyConfig:
    """Weekly section (spec M5b): in the first report of each week, about the week before."""

    writer: Callable[..., str] | None  # Claude (weekly.ClaudeWriter) or None = no commentary
    note_without_writer: str | None = None
    product_name: Callable[[str], str] = lambda key: key
    label: str = "Komentář od Claude"


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


SALE_COLUMNS = "marketplace, product_title, quantity, net_cents, currency, sold_at, product_key"


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


def month_rows(conn: sqlite3.Connection, today: date) -> list[tuple[str, str, int, str]]:
    """(currency, marketplace, net cents, sold_at) of the rows month_totals sums, for CZK conversion."""
    start = datetime(today.year, today.month, 1, tzinfo=LOCAL_TZ)
    end = datetime(today.year + today.month // 12, today.month % 12 + 1, 1, tzinfo=LOCAL_TZ)
    return conn.execute(
        "SELECT currency, marketplace, net_cents, sold_at FROM sales "
        "WHERE sold_at >= ? AND sold_at < ? AND (status = 'sold' OR quantity < 0) AND excluded = 0",
        (_utc_text(start), _utc_text(end)),
    ).fetchall()


class CzkConverter:
    """Net cents in a sale's currency → haléře at the ČNB rate of the sale's local day (fx.Rates)."""

    def __init__(self, rates):
        self.rates = rates

    def __call__(self, cents: int, currency: str, sold_at: str) -> int | None:
        rate = self.rates.rate(_local(sold_at).date(), currency)
        return None if rate is None else fx.to_czk(cents, rate)

    @property
    def error(self) -> str | None:
        return self.rates.error


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


DAY_ONLY = {"fab", "cgtrader"}  # their reports give the day, not the time


def _when(moment: datetime | str, year: int | None = None, time: bool = True) -> str:
    """'21. 11. 23:57'; with the year when it differs from `year` (the report's year)."""
    local = _local(moment)
    shown_year = f" {local.year}" if year is not None and local.year != year else ""
    clock = f" {local:%H:%M}" if time else ""
    return f"{local.day}. {local.month}.{shown_year}{clock}"


def _name(marketplace: str) -> str:
    return MARKETPLACE_NAMES.get(marketplace, marketplace)


def _approx_czk(haler: int | None, currency: str) -> str:
    if haler is None or currency == fx.HOME:
        return ""
    return f" (≈ {format_money(haler, 'Kč')})"


def _sale_line(
    row: tuple, czk=None, year: int | None = None, refund: bool = False, product_name=None
) -> str:
    """One sale: catalog product name, then the marketplace. A refund always shows a negative amount
    (Fab stores refunds as negative rows, Gumroad and Cosmos as the original sale with a refund status)."""
    marketplace, title, quantity, net, currency, sold_at, key = row
    if refund:
        quantity, net = abs(quantity), -abs(net)
    haler = czk(net, currency, sold_at) if czk else None
    when = _when(sold_at, year, time=marketplace not in DAY_ONLY)
    if net == 0 and not refund:
        amount = f"zdarma (0,00 {currency})"
    else:
        label = "vráceno" if refund else "čistě"
        amount = f"{label} {format_money(net, currency)}{_approx_czk(haler, currency)}"
    if key and product_name:
        name = product_name(key)
    else:  # not in the catalog yet: the marketplace's own title
        name = title or "(bez názvu)"
    return f"{name} ({_name(marketplace)}) – {quantity}× – {amount} ({when})"


def _new_totals(sales: list[tuple], czk) -> list[str]:
    """'čistě 63,21 USD (≈ 1 295,81 Kč)' per currency of the new sales."""
    by_currency: dict[str, list[int | None]] = {}
    for _marketplace, _title, _quantity, net, currency, sold_at, *_ in sales:
        values = by_currency.setdefault(currency, [0, 0])
        values[0] += net
        haler = (net if currency == fx.HOME else czk(net, currency, sold_at)) if czk else None
        values[1] = None if haler is None or values[1] is None else values[1] + haler
    return [
        f"čistě {format_money(net, currency)}{_approx_czk(haler, currency)}"
        for currency, (net, haler) in by_currency.items()
    ]


def _subject(
    day: date, sales: list[tuple], failed: list[StepResult], totals: list[str], stale: Sequence[str] = ()
) -> str:
    parts = []
    if failed:
        parts.append("⚠ chyba: " + ", ".join(r.step.name for r in failed))
    if stale:
        parts.append("⚠ starý report: " + ", ".join(stale))
    if sales:
        text = _plural_sales(sum(row[2] for row in sales))
        if len(totals) == 1:  # same text as the total line in the body
            text += f", {totals[0]}"
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
    czk=None,
    month_czk: dict[tuple[str, str], int | None] | None = None,
    weekly_section: Section | None = None,
    product_name=None,
    monthly_section: Section | None = None,
    manual=None,
) -> Report:
    """czk / month_czk: CZK conversion (CzkConverter, haléře per (currency, marketplace)); None = no CZK.
    manual: manual.ManualStatus per hand-uploaded source (spec M5c), shown instead of a plain "ok"."""
    failed = [r for r in results if not r.ok]
    manual_by_key = {m.key: m for m in manual or []}
    ok_keys = {r.step.key for r in results if r.ok}
    stale = [_name(m.key) for m in manual or [] if m.in_subject and m.key in ok_keys]
    totals_new = _new_totals(sales, czk)
    report = Report(_subject(day, sales, failed, totals_new, stale))
    month_czk = month_czk or {}
    if monthly_section is not None:
        report.subject += " · měsíční shrnutí"
        report.sections.append(monthly_section)
    if weekly_section is not None:
        report.subject += " · týdenní shrnutí"
        report.sections.append(weekly_section)

    report.sections.append(Section(
        "Nové prodeje od minulého souhrnu",
        [_sale_line(row, czk, day.year, product_name=product_name) for row in sales]
        + [f"Celkem nové: {total}" for total in totals_new]
        or ["Žádné nové prodeje."],
    ))
    if refunds:
        report.sections.append(Section(
            "Refundy",
            [_sale_line(row, czk, day.year, refund=True, product_name=product_name) for row in refunds],
        ))

    month_lines = []
    totals: dict[str, int] = {}
    totals_czk: dict[str, int | None] = {}
    # within a currency, the marketplace with the highest income first (same order as the weekly section)
    month = sorted(month, key=lambda r: (r[0], -(month_czk.get((r[0], r[1])) or r[3]), r[1]))
    for currency, marketplace, units, net in month:
        haler = month_czk.get((currency, marketplace))
        month_lines.append(
            f"{_name(marketplace)}: {units} ks, čistě {format_money(net, currency)}"
            f"{_approx_czk(haler, currency)}"
        )
        totals[currency] = totals.get(currency, 0) + net
        previous = totals_czk.get(currency, 0)
        totals_czk[currency] = None if haler is None or previous is None else previous + haler
    for currency, net in totals.items():
        month_lines.append(
            f"Celkem: čistě {format_money(net, currency)}{_approx_czk(totals_czk[currency], currency)}"
        )
    if len(totals) > 1 and all(totals_czk.get(c) is not None or c == fx.HOME for c in totals):
        overall = sum(totals[c] if c == fx.HOME else totals_czk[c] for c in totals)
        month_lines.append(f"Celkem ve všech měnách: ≈ {format_money(overall, 'Kč')}")
    report.sections.append(Section(
        f"Tento měsíc ({MONTHS[day.month - 1]} {day.year})",
        month_lines or ["Zatím žádné prodeje."],
    ))

    status_lines = []
    for result in results:
        if result.ok:
            extra = manual_by_key.get(result.step.key)
            status_lines.append(f"{result.step.name}: {extra.text if extra else 'ok'}")
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
    if czk is not None and czk.error:
        status_lines.append(f"Kurz ČNB: nedostupný ({czk.error}), částky v Kč chybí")
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
    make_rates=None,
    weekly_config: WeeklyConfig | None = None,
    product_name: Callable[[str], str] | None = None,
    monthly: bool = False,
    manual_dirs: tuple[Path, Path] | None = None,
) -> int:
    """Run all steps and send the report. send=None is a dry run: print only, change no state.

    make_rates(conn, today) -> fx.Rates for CZK amounts (None = original currency only);
    product_name(key) -> catalog name, so one product has one name everywhere in the report.
    monthly: add the monthly section to the first report of each month (spec M5c);
    manual_dirs: (Fab folder, CGTrader folder) to say how far the hand-uploaded reports reach.
    """
    if product_name is None and weekly_config is not None:
        product_name = weekly_config.product_name
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
        czk = CzkConverter(make_rates(conn, day)) if make_rates else None
        month_czk: dict[tuple[str, str], int | None] = {}
        if czk is not None:
            for currency, marketplace, net, sold_at in month_rows(conn, day):
                key = (currency, marketplace)
                haler = czk(net, currency, sold_at)
                previous = month_czk.get(key, 0)
                month_czk[key] = None if haler is None or previous is None else previous + haler
        week_key = weekly.last_week(day)[0].isoformat()
        weekly_section = None
        weekly_log: list[str] = []
        if weekly_config is not None and state.get("weekly_sent_for") != week_key:
            facts = weekly.week_facts(conn, day, czk, product_name or weekly_config.product_name)
            if weekly_config.writer is None:
                comment = weekly.Commentary(None, weekly_config.note_without_writer, [])
            else:
                comment = weekly.commentary(facts, weekly_config.writer)
            weekly_log = comment.log
            weekly_section = Section(
                f"Minulý týden ({facts['obdobi']})",
                weekly.fact_lines(facts) + ([comment.note] if comment.note else []),
                intro=comment.text,
                intro_label=weekly_config.label,
            )  # rejected attempts go to the log only
        monthly_section = None
        month_key = None
        if monthly:
            from sales_tracker import monthly as monthly_mod

            month_key = monthly_mod.key(day)
            if state.get("monthly_sent_for") != month_key:
                monthly_section = monthly_mod.section(conn, czk, day, product_name or (lambda k: k))
        manual = None
        if manual_dirs is not None:
            from sales_tracker import manual as manual_mod

            manual = manual_mod.statuses(conn, day, *manual_dirs)
        report = build_report(
            day=day, results=results, sales=sales, refunds=refunds, month=month, state=state,
            now=now, czk=czk, month_czk=month_czk, weekly_section=weekly_section,
            product_name=product_name, monthly_section=monthly_section, manual=manual,
        )
    finally:
        conn.close()


    log = [f"=== {now.isoformat()} ==="]
    for result in results:
        log.append(f"--- {result.step.name}: {'ok' if result.ok else 'CHYBA'} ---")
        log.append(result.output.rstrip())
    log.extend(weekly_log)
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
            if weekly_section is not None:
                state["weekly_sent_for"] = week_key
            if monthly_section is not None:
                state["monthly_sent_for"] = month_key
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
