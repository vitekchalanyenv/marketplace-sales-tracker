"""Weekly summary for the Monday report (spec M5b): code computes the numbers, Claude only comments.

Claude never writes a number. It writes the commentary with placeholders such as {cosmos_kc} or
{smer_prijmu}, and the code fills in the values. Before that, a deterministic check rejects the text
if it contains a digit, a number word or a direction word of its own (so it cannot say "rose" when
income fell), an unknown placeholder, or a placeholder that sits next to the wrong marketplace or
product (so it cannot give Cosmos the CGTrader amount). One retry with the problems named; if it
still fails, the report goes out with the code's numbers only (Vítek's decision).
"""

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Prague")
MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NAMES = {"gumroad": "Gumroad", "cosmos": "Cosmos", "fab": "Fab", "cgtrader": "CGTrader"}

SLOT_RE = re.compile(r"\{([a-z0-9_]+)\}")
DIGIT_RE = re.compile(r"\d")
NUMBER_WORD_RE = re.compile(
    r"\b(nula|nul[ay]|jed(en|na|no|nou|noho|nomu)|dv(a|ě|ou|ěma)|tř(i|ech|em)|čtyř(i|ech)?|pět|šest|"
    r"sedm|osm|devět|deset|žádn\w*|polovin\w*|dvojnásob\w*|trojnásob\w*|dvakrát|třikrát)\b",
    re.IGNORECASE,
)
DIRECTION_RE = re.compile(
    r"\b(\w*(vzr[ůo]st|kles|pokles|nárůst|narost|propad|zlepš|zhorš|zdvoj|ztroj|přibyl|ubyl)\w*|"
    r"vyšší|nižší|víc|více|méně|míň|lepší|horší|stejn\w*)\b",
    re.IGNORECASE,
)
MENTION_RE = re.compile(r"\b(gumroad|cosmos|fab|cgtrader)\w*", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

SYSTEM = """Píšeš krátký komentář k týdennímu přehledu prodejů 3D assetů pro jejich autora.
Napiš 2–4 věty česky, věcně a lidsky (co se dařilo, srovnání s předchozím týdnem, co stojí za pozornost).

Čísla do textu nepíšeš ty. Dostaneš seznam značek s hodnotami a významem a místo čísla napíšeš značku
ve složených závorkách, např. „Cosmos přinesl {cosmos_kc}.“ Hodnotu doplní program.
Text se po tobě strojově kontroluje a zamítne se, když:
- obsahuje číslici nebo číslovku slovy (jeden, dva, žádný, polovina…),
- sám říká směr změny (vzrostl, klesl, víc, méně, lepší, horší…). Na směr použij značky {smer_prijmu}
  a {smer_kusu}, např. „Příjem {smer_prijmu} o {zmena_kc}.“,
- značka u marketplace nebo produktu nestojí ve stejné větě nejblíž jeho názvu. Názvy produktů piš jen
  značkou ({produkt1} …), marketplace jménem.
Použij jen značky ze seznamu. Odpověz jen samotným komentářem, bez nadpisu a bez odrážek."""


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


# --- placeholders and the check ----------------------------------------------------------------

@dataclass(frozen=True)
class Slot:
    value: str
    meaning: str
    entity: str | None = None  # marketplace name or productN the value belongs to


def _pieces(n: int) -> str:
    if n == 1:
        return "1 kus"
    return f"{n} kusy" if 2 <= n <= 4 else f"{n} kusů"


def slots(facts: dict[str, Any]) -> dict[str, Slot]:
    """Every value Claude may use, by placeholder name. Built only from the facts."""
    prev = facts["predchozi_tyden"]
    s: dict[str, Slot] = {
        "obdobi": Slot(facts["obdobi"], "minulý týden"),
        "celkem_kusu": Slot(_pieces(facts["prodano_kusu"]), "prodáno kusů minulý týden celkem"),
        "predchozi_obdobi": Slot(prev["obdobi"], "týden předtím"),
        "predchozi_kusu": Slot(_pieces(prev["prodano_kusu"]), "prodáno kusů týden předtím"),
    }
    if facts["cisty_prijem_kc"]:
        s["celkem_kc"] = Slot(facts["cisty_prijem_kc"], "čistý příjem minulý týden celkem v Kč")
    for currency, money in facts["cisty_prijem"].items():
        s[f"celkem_{currency.lower()}"] = Slot(money, f"čistý příjem minulý týden v {currency}")
    if prev["cisty_prijem_kc"]:
        s["predchozi_kc"] = Slot(prev["cisty_prijem_kc"], "čistý příjem týden předtím v Kč")
    change = facts.get("zmena_proti_predchozimu_tydnu_kc")
    if change is not None:
        if change.startswith("-"):
            direction = "klesl"
        elif change == "0,00 Kč":
            direction = "zůstal stejný"
        else:
            direction = "vzrostl"
        s["smer_prijmu"] = Slot(direction, "jak se změnil příjem proti týdnu předtím (sloveso)")
        s["zmena_kc"] = Slot(change.removeprefix("-"), "o kolik se změnil příjem (bez znaménka)")
        percent = facts.get("zmena_proti_predchozimu_tydnu_procent")
        if percent is not None:
            s["zmena_procent"] = Slot(f"{abs(percent)} %", "o kolik procent se změnil příjem (bez znaménka)")
    units = facts["zmena_kusu"]
    s["smer_kusu"] = Slot(
        "více" if units > 0 else ("méně" if units < 0 else "stejně"),
        "prodalo se více / méně / stejně kusů než týden předtím",
    )
    s["zmena_kusu"] = Slot(_pieces(abs(units)), "o kolik kusů se to liší (bez znaménka)")
    for item in facts["podle_marketplace"]:
        key, name = item["marketplace"].lower(), item["marketplace"]
        s[f"{key}_kusu"] = Slot(_pieces(item["kusu"]), f"prodáno kusů na {name}", name)
        if item["cisty_prijem_kc"]:
            s[f"{key}_kc"] = Slot(item["cisty_prijem_kc"], f"čistý příjem z {name} v Kč", name)
    for index, item in enumerate(facts["podle_produktu"], start=1):
        key = f"produkt{index}"
        rank = " (nejprodávanější)" if index == 1 else ""
        s[key] = Slot(item["produkt"], f"název produktu{rank}")
        s[f"{key}_kusu"] = Slot(_pieces(item["kusu"]), f"prodáno kusů produktu {{{key}}}", key)
        if item["cisty_prijem_kc"]:
            s[f"{key}_kc"] = Slot(item["cisty_prijem_kc"], f"čistý příjem z produktu {{{key}}} v Kč", key)
    return s


def _mentions(sentence: str, available: dict[str, Slot]) -> list[tuple[int, str]]:
    blanked = SLOT_RE.sub(lambda m: " " * len(m.group()), sentence)  # "fab" inside {fab_kc} is no mention
    found = [(m.start(), NAMES[m.group(1).lower()]) for m in MENTION_RE.finditer(blanked)]
    found += [
        (m.start(), m.group(1)) for m in SLOT_RE.finditer(sentence)
        if m.group(1) in available and re.fullmatch(r"produkt\d+", m.group(1))
    ]
    return found


def check(text: str, available: dict[str, Slot]) -> list[str]:
    """Problems in a commentary written with placeholders. Empty list = the text passes."""
    problems = []
    unknown = sorted({name for name in SLOT_RE.findall(text) if name not in available})
    problems += [f"neznámá značka {{{name}}}" for name in unknown]
    plain = SLOT_RE.sub(" ", text)
    digits = sorted({d.strip(" ,.") for d in re.findall(r"\d[\d ,.%]*", plain)})
    if digits:
        problems.append("číslo napsané přímo: " + ", ".join(digits))
    problems += [f"číslovka slovem „{m.group()}“" for m in NUMBER_WORD_RE.finditer(plain)]
    problems += [f"vlastní směr změny „{m.group()}“" for m in DIRECTION_RE.finditer(plain)]
    for sentence in SENTENCE_END_RE.split(text):
        mentions = _mentions(sentence, available)
        for m in SLOT_RE.finditer(sentence):
            slot = available.get(m.group(1))
            if slot is None or slot.entity is None:
                continue
            if not mentions:
                problems.append(f"{{{m.group(1)}}} stojí ve větě bez názvu, ke kterému patří")
                continue
            before = [mention for mention in mentions if mention[0] < m.start()]
            # the name right before the value (Czech subject first); only without one, the next name after
            nearest = max(before)[1] if before else min(mentions)[1]
            if nearest != slot.entity:
                problems.append(f"{{{m.group(1)}}} patří k {slot.entity}, ale ve větě stojí u {nearest}")
    return problems


def render(text: str, available: dict[str, Slot]) -> str:
    return SLOT_RE.sub(lambda m: available[m.group(1)].value, text)


# --- Claude ------------------------------------------------------------------------------------

class ClaudeWriter:
    """Asks Claude for the commentary. Only the placeholder list goes in, nothing else from the database."""

    def __init__(self, api_key: str, client=None):
        if not api_key and client is None:
            raise CommentaryError("chybí ANTHROPIC_API_KEY v .env")
        if client is None:
            import anthropic  # only when the weekly summary really runs

            client = anthropic.Anthropic(api_key=api_key)
        self.client = client

    def __call__(self, available: dict[str, Slot], rejected: list[str] | None = None) -> str:
        import anthropic

        listing = {name: {"hodnota": s.value, "význam": s.meaning} for name, s in available.items()}
        content = "Značky pro minulý týden:\n" + json.dumps(listing, ensure_ascii=False, indent=2)
        if rejected:
            content += (
                "\n\nPředchozí verze komentáře neprošla kontrolou: " + "; ".join(rejected)
                + ". Napiš komentář znovu podle pravidel."
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
    text: str | None  # with the values filled in; None = not used
    note: str | None  # shown instead of / next to the text
    log: list[str]


def commentary(facts: dict[str, Any], writer: Callable[..., str] | None) -> Commentary:
    """Ask, check, retry once with the problems named, otherwise give up (Vítek's decision)."""
    if writer is None:
        return Commentary(None, None, [])
    available = slots(facts)
    log: list[str] = []
    rejected: list[str] | None = None
    for attempt in (1, 2):
        try:
            text = writer(available, rejected)
        except CommentaryError as exc:
            return Commentary(None, f"Komentář Claude chybí: {exc}.", log)
        rejected = check(text, available)
        if not rejected:
            return Commentary(render(text, available), None, log)
        log.append(f"pokus {attempt}: komentář neprošel kontrolou ({'; '.join(rejected)}): {text}")
    return Commentary(None, "Komentář Claude neprošel kontrolou čísel, posílám jen čísla.", log)
