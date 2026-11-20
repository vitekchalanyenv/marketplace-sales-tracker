"""Příkaz `sync gumroad`: chování a hlášky podle spec M1. HTTP se mockuje, DB je dočasná."""

from datetime import date

import httpx
import pytest

from sales_tracker import cli, db

TODAY = date(2026, 11, 20)


def serve(page1, page2, requests=None):
    def handler(request):
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=page2 if "page_key" in request.url.params else page1)

    return httpx.MockTransport(handler)


def run(tmp_path, transport, since=None):
    return cli.sync_gumroad(
        "test-token",
        tmp_path / "sales.db",
        since=since,
        transport=transport,
        sleep=lambda s: None,
        today=TODAY,
    )


def test_prvni_a_druhy_beh(tmp_path, capsys, page1, page2):
    assert run(tmp_path, serve(page1, page2)) == 0
    out = capsys.readouterr().out
    assert "staženo 5" in out and "nových 5" in out and "aktualizovaných 0" in out

    assert run(tmp_path, serve(page1, page2)) == 0
    out = capsys.readouterr().out
    assert "staženo 5" in out and "nových 0" in out and "aktualizovaných 0" in out

    conn = db.connect(tmp_path / "sales.db")
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 5


def test_prvni_beh_stahuje_vse(tmp_path, page1, page2):
    requests = []
    run(tmp_path, serve(page1, page2, requests))
    assert "after" not in requests[0].url.params


def test_dalsi_beh_stahuje_poslednich_30_dni(tmp_path, page1, page2):
    run(tmp_path, serve(page1, page2))
    requests = []
    run(tmp_path, serve(page1, page2, requests))
    assert requests[0].url.params["after"] == "2026-10-21"


def test_since_ma_prednost(tmp_path, page1, page2):
    requests = []
    run(tmp_path, serve(page1, page2, requests), since=date(2025, 1, 1))
    assert requests[0].url.params["after"] == "2025-01-01"


def test_refund_se_projevi_jako_aktualizace(tmp_path, capsys, page1, page2):
    run(tmp_path, serve(page1, page2))
    capsys.readouterr()

    page1["sales"][0]["refunded"] = True
    run(tmp_path, serve(page1, page2))
    out = capsys.readouterr().out
    assert "nových 0" in out and "aktualizovaných 1" in out


def test_vadny_zaznam_se_vypise_a_ostatni_ulozi(tmp_path, capsys, page1, page2):
    del page1["sales"][1]["created_at"]
    assert run(tmp_path, serve(page1, page2)) == 0
    out = capsys.readouterr().out

    assert "SAMPLE-bbbbbbbbbbbbbbbbbbbb==" in out
    assert "created_at" in out
    assert "přeskočeno 1" in out
    conn = db.connect(tmp_path / "sales.db")
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 4


def test_affiliate_vypise_upozorneni(tmp_path, capsys, page1, page2):
    run(tmp_path, serve(page1, page2))
    out = capsys.readouterr().out
    assert "affiliate" in out and "SAMPLE-bbbbbbbbbbbbbbbbbbbb==" in out


def test_vystup_neobsahuje_osobni_udaje(tmp_path, capsys, page1, page2):
    del page1["sales"][0]["price"]
    run(tmp_path, serve(page1, page2))
    out = capsys.readouterr().out
    assert "@" not in out
    assert "Sample Buyer" not in out


@pytest.mark.parametrize("status", [401, 403])
def test_neplatny_token(tmp_path, capsys, status):
    transport = httpx.MockTransport(lambda r: httpx.Response(status))
    assert run(tmp_path, transport) == 1
    assert "Token je neplatný nebo nemá oprávnění view_sales" in capsys.readouterr().out


def test_vypadek_neposkodi_db(tmp_path, capsys, page1, page2):
    run(tmp_path, serve(page1, page2))
    capsys.readouterr()

    def handler(request):
        if "page_key" in request.url.params:
            return httpx.Response(503)
        return httpx.Response(200, json=page1)

    page1["sales"][0]["refunded"] = True
    assert run(tmp_path, httpx.MockTransport(handler)) == 1
    out = capsys.readouterr().out
    assert "Nic se neuložilo" in out

    conn = db.connect(tmp_path / "sales.db")
    statuses = {r[0] for r in conn.execute("SELECT status FROM sales")}
    assert "refunded" in statuses  # 900003 ze vzorku
    first = conn.execute(
        "SELECT status FROM sales WHERE external_id = 'SAMPLE-aaaaaaaaaaaaaaaaaaaa=='"
    ).fetchone()[0]
    assert first == "sold"  # rozpracovaná změna se neuložila


def test_chybi_token(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)  # žádný .env
    monkeypatch.delenv("GUMROAD_ACCESS_TOKEN", raising=False)

    assert cli.main(["sync", "gumroad"]) == 1
    out = capsys.readouterr().out
    assert "Chybí GUMROAD_ACCESS_TOKEN v .env" in out
    assert "Traceback" not in out


def test_since_ve_spatnem_formatu(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["sync", "gumroad", "--since", "20.11.2026"])
    assert exc.value.code == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err
