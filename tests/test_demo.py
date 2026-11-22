"""Demo režim (spec M5b): doběhne bez sítě a účtů a nesáhne na data/private/."""

import os

from sales_tracker import cli


def test_demo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # výchozí cesty data/private/… by vznikly tady
    for name in ("GUMROAD_ACCESS_TOKEN", "RESEND_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    for marketplace in ("Gumroad", "Cosmos", "Fab", "CGTrader"):
        assert f"--- {marketplace}: ok ---" in out
    assert "Prodeje 26. 1.: 4 nové prodeje, čistě 63,21 USD (≈ 1 295,81 Kč) · týdenní shrnutí" in out
    assert "- Celkem nové: čistě 63,21 USD (≈ 1 295,81 Kč)" in out  # předmět = tělo
    assert "TENTO MĚSÍC (LEDEN 2026)" in out
    assert out.count("Nespárované listingy") == 1  # párování jednou na konci, ne po každém zdroji
    assert "Proti týdnu předtím příjem klesl o 19 %." in out  # směr dosadil kód
    assert "pokus 1: komentář neprošel kontrolou" in out  # zamítnutý pokus jen v logu,
    assert "Zamítnutý" not in out and "{cgtrader_kc}" not in out.split("--- souhrn")[1]  # ne v e-mailu
    assert "Ukázkový komentář (ne od Claude): Za týden 19. 1. – 25. 1. 2026" in out
    assert "(≈ " in out  # částky v Kč (vymyšlený kurz)
    assert "zkušební běh, e-mail se neposlal" in out
    assert os.listdir(tmp_path) == []  # nic nevzniklo v pracovní složce


def test_demo_je_pokazde_stejne(capsys):
    cli.main(["demo"])
    first = capsys.readouterr().out
    cli.main(["demo"])
    assert capsys.readouterr().out == first
