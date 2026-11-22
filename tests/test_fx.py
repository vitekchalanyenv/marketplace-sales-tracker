"""Kurzy ČNB (spec M5b). Bez sítě: text odpovědi je ve tvaru ověřeném 2026-11-22, hodnoty vymyšlené."""

import sqlite3
from datetime import date
from decimal import Decimal

import httpx
import pytest

from sales_tracker import fx

CNB = (
    "20.11.2026 #223\n"
    "země|měna|množství|kód|kurz\n"
    "EMU|euro|1|EUR|25,000\n"
    "Filipíny|peso|100|PHP|40,000\n"
    "USA|dolar|1|USD|20,000\n"
)


def test_parse():
    valid, rates = fx.parse_cnb(CNB)
    assert valid == date(2026, 11, 20)
    assert rates["USD"] == Decimal("20.000")
    assert rates["PHP"] == Decimal("0.4")  # kurz za 100 jednotek


@pytest.mark.parametrize("text", [
    "", "20.11.2026 #223\nšpatná hlavička\nUSA|dolar|1|USD|20,0",
    "xx #1\nzemě|měna|množství|kód|kurz\nUSA|dolar|1|USD|20,0",
    "20.11.2026 #223\nzemě|měna|množství|kód|kurz\nUSA|dolar|1|USD|abc",
    "20.11.2026 #223\nzemě|měna|množství|kód|kurz\nUSA|dolar|USD|20,0",
])
def test_parse_chyby(text):
    with pytest.raises(fx.FxError):
        fx.parse_cnb(text)


def test_to_czk():
    assert fx.to_czk(4991, Decimal("22.262")) == 111110  # 49,91 USD × 22,262 = 1 111,10 Kč
    assert fx.to_czk(1, Decimal("22.265")) == 22  # 0,22265 Kč → 22 haléřů (ROUND_HALF_UP)
    assert fx.to_czk(-500, Decimal(20)) == -10000


def test_cache_a_dnesek():
    conn = sqlite3.connect(":memory:")
    calls = []

    def fetch(day):
        calls.append(day)
        return CNB

    rates = fx.Rates(conn, today=date(2026, 11, 22), fetch=fetch)
    assert rates.rate(date(2026, 11, 20), "USD") == Decimal("20.000")
    assert rates.rate(date(2026, 11, 20), "EUR") == Decimal("25.000")  # z mezipaměti
    assert rates.rate(date(2026, 11, 22), "USD") == Decimal("20.000")  # dnešek
    assert rates.rate(date(2026, 11, 22), "USD") == Decimal("20.000")
    assert calls == [date(2026, 11, 20), date(2026, 11, 22), date(2026, 11, 22)]  # dnešek se neukládá
    assert rates.rate(date(2026, 11, 20), "CZK") == 1


def test_vypadek_jen_jeden_pokus():
    calls = []

    def fetch(day):
        calls.append(day)
        raise fx.FxError("ČNB není dostupná (ConnectError)")

    rates = fx.Rates(sqlite3.connect(":memory:"), today=date(2026, 11, 22), fetch=fetch)
    assert rates.rate(date(2026, 11, 1), "USD") is None
    assert rates.rate(date(2026, 11, 2), "USD") is None
    assert len(calls) == 1 and "ČNB" in rates.error


def test_fetch_url_a_datum():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=CNB)

    assert fx.fetch_cnb(date(2026, 1, 5), transport=httpx.MockTransport(handler)) == CNB
    assert seen[0].url.params["date"] == "05.01.2026"
    assert str(seen[0].url).startswith(fx.CNB_URL)

    with pytest.raises(fx.FxError, match="HTTP 500"):
        fx.fetch_cnb(date(2026, 1, 5), transport=httpx.MockTransport(lambda r: httpx.Response(500)))
