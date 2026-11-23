"""Exchange rates from the Czech National Bank (ČNB) for CZK totals (spec M5b).

Sales stay stored in their original currency; only totals are converted, at the ČNB rate valid on
the local day of the sale. Format verified 2026-11-22: for a weekend or holiday ČNB returns the
last valid rate, and before ~14:30 "today" still returns the previous working day's rate, so a rate
for today is used but never cached.
"""

import sqlite3
import ssl
import time
from collections.abc import Callable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx

CNB_URL = (
    "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/"
    "kurzy-devizoveho-trhu/denni_kurz.txt"
)
HOME = "CZK"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fx_rates (
    day          TEXT NOT NULL,  -- local day of the sale (YYYY-MM-DD)
    currency     TEXT NOT NULL,
    czk_per_unit TEXT NOT NULL,  -- Decimal as text, never float
    PRIMARY KEY (day, currency)
);
"""


class FxError(Exception):
    """Rates could not be loaded (network, unexpected format)."""


def parse_cnb(text: str) -> tuple[date, dict[str, Decimal]]:
    """'20.11.2026 #223', header, then 'USA|dolar|1|USD|22,262' rows → (valid day, CZK per 1 unit)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or lines[1] != "země|měna|množství|kód|kurz":
        raise FxError("neočekávaný formát kurzů ČNB")
    try:
        valid = datetime.strptime(lines[0].split()[0], "%d.%m.%Y").date()
    except (ValueError, IndexError):
        raise FxError(f"neočekávané datum v kurzech ČNB: {lines[0]!r}") from None
    rates = {}
    for line in lines[2:]:
        parts = line.split("|")
        if len(parts) != 5:
            raise FxError(f"neočekávaný řádek kurzů ČNB: {line!r}")
        try:
            amount = Decimal(parts[2])
            rate = Decimal(parts[4].replace(",", "."))
        except InvalidOperation:
            raise FxError(f"neočekávaný řádek kurzů ČNB: {line!r}") from None
        if amount <= 0 or rate <= 0:
            raise FxError(f"neočekávaný řádek kurzů ČNB: {line!r}")
        rates[parts[3]] = rate / amount
    return valid, rates


def fetch_cnb(day: date, transport: httpx.BaseTransport | None = None) -> str:
    try:
        with httpx.Client(
            timeout=30, transport=transport, verify=ssl.create_default_context()
        ) as client:
            response = client.get(CNB_URL, params={"date": day.strftime("%d.%m.%Y")})
    except httpx.HTTPError as exc:
        raise FxError(f"ČNB není dostupná ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise FxError(f"ČNB vrátila HTTP {response.status_code}")
    return response.text


def polite(fetch: Callable[[date], str], pause: float = 1.0, sleep=time.sleep) -> Callable[[date], str]:
    """The same fetch, with a pause between requests (the dashboard may need rates for many old
    days at once; spec M6: one by one, gently)."""
    calls = 0

    def fetch_politely(day: date) -> str:
        nonlocal calls
        if calls:
            sleep(pause)
        calls += 1
        return fetch(day)

    return fetch_politely


class Rates:
    """CZK per unit for (day, currency), cached in the fx_rates table. Unknown → None."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        today: date,
        fetch: Callable[[date], str] = fetch_cnb,
    ):
        self.conn = conn
        self.today = today
        self.fetch = fetch
        self.error: str | None = None
        conn.executescript(SCHEMA)

    def rate(self, day: date, currency: str) -> Decimal | None:
        if currency == HOME:
            return Decimal(1)
        row = self.conn.execute(
            "SELECT czk_per_unit FROM fx_rates WHERE day = ? AND currency = ?",
            (day.isoformat(), currency),
        ).fetchone()
        if row is not None:
            return Decimal(row[0])
        if self.error is not None:
            return None  # one failed download per run is enough
        try:
            _, rates = parse_cnb(self.fetch(day))
        except FxError as exc:
            self.error = str(exc)
            return None
        if day < self.today:  # today's rate may still change in the afternoon
            with self.conn:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO fx_rates (day, currency, czk_per_unit) VALUES (?, ?, ?)",
                    [(day.isoformat(), code, str(value)) for code, value in rates.items()],
                )
        return rates.get(currency)


def to_czk(cents: int, rate: Decimal) -> int:
    """Amount in cents of a foreign currency → haléře, rounded half up."""
    return int((Decimal(cents) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))
