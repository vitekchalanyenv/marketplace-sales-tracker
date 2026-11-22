"""Weekly summary for the Monday report (spec M5b): code computes the numbers, Claude only comments.

The commentary is checked deterministically before it is used: every number in the text must be
one of the numbers in the facts Claude was given (percentages within 1 point). One retry with the
offending numbers named; if it still fails, the report goes out with the code's numbers only.
"""

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Prague")
MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NAMES = {"gumroad": "Gumroad", "cosmos": "Cosmos", "fab": "Fab", "cgtrader": "CGTrader"}
WORD_NUMBERS = {
    "jeden": 1, "jedna": 1, "jedno": 1, "dva": 2, "dvě": 2, "tři": 3, "čtyři": 4, "pět": 5,
    "šest": 6, "sedm": 7, "osm": 8, "devět": 9, "deset": 10,
}
NUMBER_RE = re.compile(r"\d{1,3}(?:[  ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")
PERCENT_AFTER_RE = re.compile(r"^\s*(%|procent)")
WORD_RE = re.compile(r"\b(" + "|".join(WORD_NUMBERS) + r")\b", re.IGNORECASE)

SYSTEM = """Píšeš krátký komentář k týdennímu přehledu prodejů 3D assetů pro jejich autora.
Dostaneš hotová čísla jako JSON. Napiš 2–4 věty česky, věcně a lidsky (co se dařilo, srovnání s předchozím
týdnem, co stojí za pozornost).

Pravidla pro čísla jsou přísná a text se po tobě strojově kontroluje:
- Používej jen čísla, která v datech doslova jsou, a piš je stejně jako v datech (např. „45,90 USD“).
- Nic nepočítej: žádné nové součty, rozdíly, průměry ani procenta, která v datech nejsou.
- Když nějaké číslo v datech není, napiš to bez čísla.
Odpověz jen samotným komentářem, bez nadpisu a bez odrážek."""


class CommentaryError(Exception):
    """Claude could not be asked (no key, network, refusal). The report goes out without commentary."""


# --- facts -------------------------------------------------------------------------------------

def last_week(day: date) -> tuple[date, date]:
    """Monday and Sunday of the week before the week containing `day`."""
    monday = day - timedelta(days=day.weekday())
    return monday - timedelta(days=7), monday - timedelta(days=1)


def _utc_bounds(first: date, last: date) -> tuple[str, str]:
    start = datetime(first.year, first.month, first.day, tzinfo=LOCAL_TZ)
    end = datetime(last.year, last.month, last.day, tzinfo=LOCAL_TZ) + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.astimezone(UTC).strftime(fmt), end.astimezone(UTC).strftime(fmt)


def _rows(conn: sqlite3.Connection, first: date, last: date) -> list[tuple]:
    start, end = _utc_bounds(first, last)
    return conn.execute(
        "SELECT marketplace, COALESCE(product_key, product_title, '?'), quantity, net_cents, currency, "
        "sold_at, status FROM sales WHERE sold_at >= ? AND sold_at < ? AND excluded = 0 "
        "AND (status = 'sold' OR quantity < 0)",
        (start, end),
    ).fetchall()


def _money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", " ") + f",{rest:02d} {currency}"


def _period(first: date, last: date) -> str:
    return f"{first.day}. {first.month}. – {last.day}. {last.month}. {last.year}"


@dataclass
class _Total:
    units: int = 0
    czk: int | None = 0

    def add(self, units: int, haler: int | None) -> None:
        self.units += units
        self.czk = None if haler is None or self.czk is None else self.czk + haler


def week_facts(
    conn: sqlite3.Connection,
    day: date,
    czk: Callable[[int, str, str], int | None] | None,
    product_name: Callable[[str], str] = lambda key: key,
) -> dict[str, Any]:
    """The numbers for last week, already formatted. This dict is all Claude ever sees."""
    first, last = last_week(day)
    prev_first, prev_last = first - timedelta(days=7), last - timedelta(days=7)

    def convert(net: int, currency: str, sold_at: str) -> int | None:
        if currency == "CZK":
            return net
        return czk(net, currency, sold_at) if czk else None

    def totals(rows):
        by_mp: dict[str, _Total] = {}
        by_product: dict[str, _Total] = {}
        native: dict[str, int] = {}
        whole = _Total()
        for marketplace, product, units, net, currency, sold_at, _status in rows:
            haler = convert(net, currency, sold_at)
            by_mp.setdefault(marketplace, _Total()).add(units, haler)
            by_product.setdefault(product, _Total()).add(units, haler)
            native[currency] = native.get(currency, 0) + net
            whole.add(units, haler)
        return by_mp, by_product, native, whole

    by_mp, by_product, native, whole = totals(_rows(conn, first, last))
    _, _, _, previous = totals(_rows(conn, prev_first, prev_last))

    def kc(value: int | None) -> str | None:
        return None if value is None else _money(value, "Kč")

    facts: dict[str, Any] = {
        "obdobi": _period(first, last),
        "prodano_kusu": whole.units,
        "cisty_prijem": {c: _money(v, c) for c, v in sorted(native.items())},
        "cisty_prijem_kc": kc(whole.czk),
        "podle_marketplace": [
            {"marketplace": NAMES.get(m, m), "kusu": t.units, "cisty_prijem_kc": kc(t.czk)}
            for m, t in sorted(by_mp.items(), key=lambda kv: (-kv[1].units, kv[0]))
        ],
        "podle_produktu": [
            {"produkt": product_name(p), "kusu": t.units, "cisty_prijem_kc": kc(t.czk)}
            for p, t in sorted(by_product.items(), key=lambda kv: (-kv[1].units, kv[0]))
        ],
        "predchozi_tyden": {
            "obdobi": _period(prev_first, prev_last),
            "prodano_kusu": previous.units,
            "cisty_prijem_kc": kc(previous.czk),
        },
    }
    if facts["podle_produktu"]:
        facts["nejprodavanejsi_produkt"] = facts["podle_produktu"][0]["produkt"]
    if whole.czk is not None and previous.czk is not None:
        facts["zmena_proti_predchozimu_tydnu_kc"] = _money(whole.czk - previous.czk, "Kč")
        if previous.czk > 0:
            facts["zmena_proti_predchozimu_tydnu_procent"] = round(
                (whole.czk - previous.czk) * 100 / previous.czk
            )
    facts["zmena_kusu"] = whole.units - previous.units
    return facts


def fact_lines(facts: dict[str, Any]) -> list[str]:
    """The code's numbers as report lines (always shown, with or without commentary)."""
    if facts["cisty_prijem"]:
        money = ", ".join(facts["cisty_prijem"].values())
        czk = f" (≈ {facts['cisty_prijem_kc']})" if facts["cisty_prijem_kc"] else ""
        lines = [f"Celkem: {facts['prodano_kusu']} ks, čistě {money}{czk}"]
    else:
        lines = ["Celkem: 0 ks, žádné prodeje"]
    for item in facts["podle_marketplace"]:
        lines.append(f"{item['marketplace']}: {item['kusu']} ks" + (
            f", ≈ {item['cisty_prijem_kc']}" if item["cisty_prijem_kc"] else ""))
    if facts.get("nejprodavanejsi_produkt"):
        lines.append(f"Nejprodávanější: {facts['nejprodavanejsi_produkt']}")
    prev = facts["predchozi_tyden"]
    change = facts.get("zmena_proti_predchozimu_tydnu_procent")
    lines.append(
        f"Předchozí týden ({prev['obdobi']}): {prev['prodano_kusu']} ks"
        + (f", ≈ {prev['cisty_prijem_kc']}" if prev["cisty_prijem_kc"] else "")
        + (f" (změna {change:+d} %)" if change is not None else "")
    )
    return lines


# --- the check ---------------------------------------------------------------------------------

def _normalize(token: str) -> Decimal | None:
    text = token.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(text).normalize()
    except InvalidOperation:
        return None


def _allowed(facts: Any) -> set[Decimal]:
    found: set[Decimal] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            found.add(Decimal(value).normalize())
            found.add(Decimal(abs(value)).normalize())  # "o 3 kusy méně" for zmena_kusu = -3
        elif isinstance(value, str):
            for token in NUMBER_RE.findall(value):
                number = _normalize(token)
                if number is not None:
                    found.add(number)
                    found.add(abs(number))

    walk(facts)
    return found


def check(text: str, facts: dict[str, Any]) -> list[str]:
    """Numbers in the commentary that are not in the facts. Empty list = the text passes."""
    allowed = _allowed(facts)
    percents = {abs(Decimal(facts[k])) for k in facts if k.endswith("_procent")}
    bad = []
    for match in NUMBER_RE.finditer(text):
        number = _normalize(match.group())
        if number is None:
            bad.append(match.group())
            continue
        is_percent = PERCENT_AFTER_RE.match(text[match.end():]) is not None
        if is_percent:
            if not any(abs(number - p) <= 1 for p in percents):
                bad.append(match.group() + " %")
        elif number not in allowed:
            bad.append(match.group())
    for match in WORD_RE.finditer(text):
        if Decimal(WORD_NUMBERS[match.group().lower()]) not in allowed:
            bad.append(match.group())
    return bad


# --- Claude ------------------------------------------------------------------------------------

class ClaudeWriter:
    """Asks Claude for the commentary. Facts go in as JSON; nothing else from the database."""

    def __init__(self, api_key: str, client=None):
        if not api_key and client is None:
            raise CommentaryError("chybí ANTHROPIC_API_KEY v .env")
        if client is None:
            import anthropic  # only when the weekly summary really runs

            client = anthropic.Anthropic(api_key=api_key)
        self.client = client

    def __call__(self, facts: dict[str, Any], rejected: list[str] | None = None) -> str:
        import anthropic

        content = "Data za minulý týden:\n" + json.dumps(facts, ensure_ascii=False, indent=2)
        if rejected:
            content += (
                "\n\nPředchozí verze komentáře obsahovala čísla, která v datech nejsou: "
                + ", ".join(rejected) + ". Napiš komentář znovu a použij jen čísla z dat."
            )
        try:
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=2000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_config={"effort": "low"},
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.AuthenticationError:
            raise CommentaryError("neplatný ANTHROPIC_API_KEY") from None
        except anthropic.RateLimitError:
            raise CommentaryError("překročen limit API Anthropicu") from None
        except anthropic.APIStatusError as exc:
            raise CommentaryError(f"API Anthropicu vrátilo HTTP {exc.status_code}") from None
        except anthropic.APIConnectionError:
            raise CommentaryError("API Anthropicu není dostupné") from None
        if response.stop_reason == "refusal":
            raise CommentaryError("Claude odmítl odpovědět")
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise CommentaryError("Claude vrátil prázdnou odpověď")
        return text


@dataclass(frozen=True)
class Commentary:
    text: str | None  # None = not used
    note: str | None  # shown instead of / next to the text
    log: list[str]


def commentary(facts: dict[str, Any], writer: Callable[..., str] | None) -> Commentary:
    """Ask, check, retry once with the bad numbers named, otherwise give up (Vítek's decision)."""
    if writer is None:
        return Commentary(None, None, [])
    log: list[str] = []
    rejected: list[str] | None = None
    for attempt in (1, 2):
        try:
            text = writer(facts, rejected)
        except CommentaryError as exc:
            return Commentary(None, f"Komentář Claude chybí: {exc}.", log)
        rejected = check(text, facts)
        if not rejected:
            return Commentary(text, None, log)
        log.append(f"pokus {attempt}: komentář neprošel kontrolou čísel {rejected}: {text}")
    return Commentary(None, "Komentář Claude neprošel kontrolou čísel, posílám jen čísla.", log)
