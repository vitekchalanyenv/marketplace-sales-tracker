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
    assert "Prodeje 26. 1.:" in out and "TENTO MĚSÍC (LEDEN 2026)" in out
    assert "(≈ " in out  # částky v Kč (vymyšlený kurz)
    assert "zkušební běh, e-mail se neposlal" in out
    assert os.listdir(tmp_path) == []  # nic nevzniklo v pracovní složce


def test_demo_je_pokazde_stejne(capsys):
    cli.main(["demo"])
    first = capsys.readouterr().out
    cli.main(["demo"])
    assert capsys.readouterr().out == first
