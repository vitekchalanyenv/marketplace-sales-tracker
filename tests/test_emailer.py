"""Odeslání souhrnu přes Resend s podvrženým HTTP (bez sítě)."""

import json

import httpx
import pytest

from sales_tracker.emailer import DEFAULT_FROM, RESEND_URL, EmailError, send_email

KEY = "re_test_vymysleny_klic"


def transport(status, body, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler)


def send(t, **kw):
    args = {"api_key": KEY, "to": "vitek@example.org", "subject": "Prodeje", "text": "t", "html": "<p>h</p>"}
    args.update(kw)
    return send_email(args.pop("api_key"), args.pop("to"), args.pop("subject"), args.pop("text"),
                      args.pop("html"), transport=t, **args)


def test_odeslani():
    seen = []
    assert send(transport(200, {"id": "abc-123"}, seen)) == "abc-123"
    request = seen[0]
    assert request.method == "POST" and str(request.url) == RESEND_URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "from": DEFAULT_FROM, "to": ["vitek@example.org"], "subject": "Prodeje",
        "text": "t", "html": "<p>h</p>",
    }


@pytest.mark.parametrize(("status", "hint"), [
    (401, "neplatný RESEND_API_KEY"),
    (403, "jen na e-mail účtu Resend"),
    (429, "limit"),
    (500, "Resend vrátil chybu"),
])
def test_chyby(status, hint):
    with pytest.raises(EmailError) as exc:
        send(transport(status, {"name": "x", "message": "důvod od Resendu"}))
    assert hint in str(exc.value) and f"HTTP {status}" in str(exc.value)
    assert "důvod od Resendu" in str(exc.value)
    assert KEY not in str(exc.value)


def test_chybi_nastaveni():
    with pytest.raises(EmailError, match="RESEND_API_KEY"):
        send(transport(200, {"id": "x"}), api_key="")


def test_vypadek_site():
    def handler(request):
        raise httpx.ConnectError("nelze se připojit")

    with pytest.raises(EmailError, match="není dostupný"):
        send(httpx.MockTransport(handler))
