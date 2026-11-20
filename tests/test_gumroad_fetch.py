"""Stahování z Gumroad API: stránkování, autentizace, opakování pokusů. HTTP se mockuje, nic nejde ven."""

from datetime import date

import httpx
import pytest

from sales_tracker.gumroad import GumroadAuthError, GumroadClient, GumroadError

TOKEN = "test-token-not-real"


def make_client(handler, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return GumroadClient(TOKEN, transport=httpx.MockTransport(handler), sleep=sleeps.append)


def test_stahne_obe_stranky(page1, page2):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "page_key" in request.url.params:
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    records = make_client(handler).fetch_sales()

    assert [r["order_id"] for r in records] == [900001, 900002, 900003, 900004, 900005]
    assert len(requests) == 2
    assert requests[0].url.path == "/v2/sales"
    assert "page_key" not in requests[0].url.params
    assert requests[1].url.params["page_key"] == page1["next_page_key"]


def test_token_jde_v_hlavicce_ne_v_url(page2):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=page2)

    make_client(handler).fetch_sales()

    assert requests[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(requests[0].url)


def test_after_se_posle_na_vsech_strankach(page1, page2):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=page2 if "page_key" in request.url.params else page1)

    make_client(handler).fetch_sales(after=date(2026, 10, 1))

    assert [r.url.params["after"] for r in requests] == ["2026-10-01", "2026-10-01"]


def test_mezi_strankami_je_pauza(page1, page2):
    sleeps = []

    def handler(request):
        return httpx.Response(200, json=page2 if "page_key" in request.url.params else page1)

    make_client(handler, sleeps).fetch_sales()

    assert len(sleeps) == 1 and sleeps[0] > 0


def test_prazdny_ucet():
    """Skutečná odpověď z 2026-11-20: účet bez prodejů."""
    client = make_client(lambda r: httpx.Response(200, json={"success": True, "sales": []}))
    assert client.fetch_sales() == []


@pytest.mark.parametrize("status", [401, 403])
def test_neplatny_token(status):
    client = make_client(lambda r: httpx.Response(status, json={"success": False}))
    with pytest.raises(GumroadAuthError):
        client.fetch_sales()


def test_5xx_se_zkusi_znovu_a_pak_projde(page2):
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=page2)

    records = make_client(handler, sleeps).fetch_sales()

    assert len(records) == 2
    assert len(calls) == 3
    assert len(sleeps) == 2


def test_5xx_po_trech_pokusech_skonci_chybou():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(502)

    with pytest.raises(GumroadError):
        make_client(handler).fetch_sales()
    assert len(calls) == 3


def test_vypadek_site_se_zkusi_znovu():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("no network", request=request)

    with pytest.raises(GumroadError) as exc:
        make_client(handler).fetch_sales()
    assert len(calls) == 3
    assert TOKEN not in str(exc.value)


def test_jina_4xx_se_neopakuje():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"success": False, "message": "Invalid page_key."})

    with pytest.raises(GumroadError) as exc:
        make_client(handler).fetch_sales()
    assert len(calls) == 1
    assert "Invalid page_key." in str(exc.value)


@pytest.mark.parametrize(
    "body",
    [{"success": False, "message": "nope"}, {"success": True}, {"success": True, "sales": {}}],
)
def test_neocekavany_tvar_odpovedi(body):
    with pytest.raises(GumroadError):
        make_client(lambda r: httpx.Response(200, json=body)).fetch_sales()


def test_odpoved_neni_json():
    with pytest.raises(GumroadError):
        make_client(lambda r: httpx.Response(200, text="<html>")).fetch_sales()
