"""Daily agent (spec M5): run every source, log the output, notify about new sales and failures.

Steps are the existing commands (sync gumroad, sync cosmos, import fab). Each runs on its own, so
one failing source does not stop the others. New sales and refunds are found by comparing the
database before and after the steps, so the steps themselves need no changes.
"""

import io
import json
import sqlite3
import traceback
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sales_tracker import db

WATCHED = ("gumroad", "cosmos")  # automatic sources; Fab is uploaded by hand
STALE_DAYS = 3
LOG_KEEP_DAYS = 60
COSMOS_LOGIN_HINT = "sync cosmos --login"
MAX_MESSAGE = 160
LOCAL_TZ = ZoneInfo("Europe/Prague")

Notify = Callable[[str, list[str]], None]


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
    error: str | None  # short, safe for a notification


@dataclass(frozen=True)
class Snapshot:
    max_rowid: int
    not_sold: set[tuple[str, str]]


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


def snapshot(conn: sqlite3.Connection) -> Snapshot:
    max_rowid = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM sales").fetchone()[0]
    rows = conn.execute("SELECT marketplace, external_id FROM sales WHERE status != 'sold'")
    return Snapshot(max_rowid, {tuple(row) for row in rows})


def new_sales(conn: sqlite3.Connection, before: Snapshot) -> list[tuple[str, str, int, int]]:
    """(currency, marketplace, units, net cents) of sales added since the snapshot."""
    return conn.execute(
        "SELECT currency, marketplace, SUM(quantity), SUM(net_cents) FROM sales "
        "WHERE rowid > ? AND status = 'sold' GROUP BY currency, marketplace "
        "ORDER BY currency, marketplace",
        (before.max_rowid,),
    ).fetchall()


def new_refunds(conn: sqlite3.Connection, before: Snapshot) -> int:
    rows = conn.execute("SELECT marketplace, external_id FROM sales WHERE status != 'sold'")
    return len({tuple(row) for row in rows} - before.not_sold)


def format_money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", " ") + f",{rest:02d} {currency}"


def _plural_sales(n: int) -> str:
    if n == 1:
        return "1 nový prodej"
    return f"{n} nové prodeje" if 2 <= n <= 4 else f"{n} nových prodejů"


def _plural_days(n: int) -> str:
    if n == 1:
        return "1 dnem"
    return f"{n} dny"


def sales_lines(rows: list[tuple[str, str, int, int]]) -> list[str]:
    by_currency: dict[str, list[tuple[str, int, int]]] = {}
    for currency, marketplace, units, net in rows:
        by_currency.setdefault(currency, []).append((marketplace, units, net))
    lines = []
    for currency, parts in by_currency.items():
        units = sum(p[1] for p in parts)
        net = sum(p[2] for p in parts)
        detail = ", ".join(
            f"{m.capitalize()} {u}" for m, u, _ in sorted(parts, key=lambda p: (-p[1], p[0]))
        )
        lines.append(f"{_plural_sales(units)}, čistě {format_money(net, currency)} ({detail})")
    return lines


def _load_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        state = {}
    state.setdefault("last_success", {})
    return state


def _days_since(state: dict, key: str, now: datetime) -> int | None:
    value = state["last_success"].get(key)
    if value is None:
        return None
    return (now - datetime.fromisoformat(value)).days


def _prune_logs(log_dir: Path, today: date) -> None:
    cutoff = today - timedelta(days=LOG_KEEP_DAYS)
    for path in log_dir.glob("daily_*.log"):
        try:
            day = date.fromisoformat(path.stem.removeprefix("daily_"))
        except ValueError:
            continue
        if day < cutoff:
            path.unlink()


def run_daily(
    steps: Sequence[Step],
    *,
    db_path: Path,
    state_path: Path,
    log_dir: Path,
    notify: Notify,
    now: datetime,
) -> int:
    conn = db.connect(db_path)
    try:
        before = snapshot(conn)
    finally:
        conn.close()

    results = [run_step(step) for step in steps]

    conn = db.connect(db_path)
    try:
        lines = sales_lines(new_sales(conn, before))
        refunds = new_refunds(conn, before)
    finally:
        conn.close()
    if refunds:
        lines.append("1 refund" if refunds == 1 else f"refundů: {refunds}")

    state = _load_state(state_path)
    for result in results:
        if result.ok:
            if result.step.key in WATCHED:
                state["last_success"][result.step.key] = now.isoformat()
            continue
        message = f"{result.step.name}: {result.error}"
        days = _days_since(state, result.step.key, now) if result.step.key in WATCHED else None
        if days is not None and days >= STALE_DAYS:
            message += f" (naposledy staženo před {_plural_days(days)})"
        lines.append(message)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    failed = any(not r.ok for r in results)
    log = [f"=== {now.isoformat()} ==="]
    for result in results:
        log.append(f"--- {result.step.name}: {'ok' if result.ok else 'CHYBA'} ---")
        log.append(result.output.rstrip())
    log.append("--- shrnutí ---")
    log.extend(lines or ["nic nového"])

    if lines:
        title = "Prodeje: něco selhalo" if failed else "Prodeje: nové prodeje"
        try:
            notify(title, lines)
        except Exception as exc:  # noqa: BLE001 – the log is the fallback
            log.append(f"notifikace se nezobrazila: {type(exc).__name__}: {exc}")

    log_dir.mkdir(parents=True, exist_ok=True)
    today = now.astimezone(LOCAL_TZ).date()
    with (log_dir / f"daily_{today.isoformat()}.log").open("a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    _prune_logs(log_dir, today)

    print("\n".join(log))
    return 1 if failed else 0


def windows_notify(title: str, lines: list[str]) -> None:
    from windows_toasts import Toast, WindowsToaster  # Windows only, imported when the agent runs

    WindowsToaster("Prodeje").show_toast(Toast(text_fields=[title, "\n".join(lines)]))
