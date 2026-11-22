"""Týdenní shrnutí (spec M5b): čísla od kódu, komentář od Claude (podvržený) a kontrola čísel."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from sales_tracker import db, weekly
from sales_tracker.models import Sale, Status

MONDAY = date(2026, 1, 26)  # minulý týden = 19. 1. – 25. 1. 2026, předchozí = 12. 1. – 18. 1.


def sale(eid, net, when, *, marketplace="cosmos", product="medieval-village", quantity=1,
         status=Status.SOLD, currency="USD"):
    return Sale(
        marketplace=marketplace, external_id=eid, product_title=product, product_ref=None,
        sold_at=when, gross_cents=abs(net) * 2, net_cents=net, currency=currency, status=status,
        raw={}, quantity=quantity,
    )


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "sales.db")
    db.upsert_sales(conn, [
        sale("a", 1000, datetime(2026, 1, 19, 8, 0, tzinfo=UTC)),
        sale("b", 2000, datetime(2026, 1, 25, 22, 30, tzinfo=UTC)),  # 25. 1. 23:30 v Praze = ještě týden
        sale("c", 500, datetime(2026, 1, 21, 9, 0, tzinfo=UTC), marketplace="fab", product="scifi-hangar"),
        sale("d", 9999, datetime(2026, 1, 25, 23, 30, tzinfo=UTC)),  # 26. 1. 0:30 v Praze = už ne
        sale("e", 1500, datetime(2026, 1, 14, 9, 0, tzinfo=UTC)),  # předchozí týden
        sale("f", 700, datetime(2026, 1, 20, 9, 0, tzinfo=UTC), status=Status.REFUNDED),  # nepočítá se
        sale("g", -500, datetime(2026, 1, 22, 0, 0, tzinfo=UTC), marketplace="fab",
             product="scifi-hangar", quantity=-1, status=Status.REFUNDED),  # Fab refund se odečte
    ])
    return conn


def czk20(net, currency, sold_at):
    return net * 20


def facts(conn, czk=czk20):
    return weekly.week_facts(conn, MONDAY, czk, {"medieval-village": "Medieval Village"}.get)


def test_tyden_po_ne_v_mistnim_case(conn):
    f = facts(conn)
    assert f["obdobi"] == "19. 1. – 25. 1. 2026"
    assert f["prodano_kusu"] == 2  # a, b, c = 3 kusy, Fab refund g jeden odečte
    assert f["cisty_prijem"] == {"USD": "30,00 USD"}  # 10 + 20 + 5 − 5
    assert f["cisty_prijem_kc"] == "600,00 Kč"
    assert f["podle_marketplace"] == [
        {"marketplace": "Cosmos", "kusu": 2, "cisty_prijem_kc": "600,00 Kč"},
        {"marketplace": "Fab", "kusu": 0, "cisty_prijem_kc": "0,00 Kč"},
    ]
    assert f["nejprodavanejsi_produkt"] == "Medieval Village"
    assert f["predchozi_tyden"] == {"obdobi": "12. 1. – 18. 1. 2026", "prodano_kusu": 1,
                                    "cisty_prijem_kc": "300,00 Kč"}
    assert f["zmena_proti_predchozimu_tydnu_kc"] == "300,00 Kč"
    assert f["zmena_proti_predchozimu_tydnu_procent"] == 100
    assert f["zmena_kusu"] == 1


def test_bez_kurzu(conn):
    f = facts(conn, czk=None)
    assert f["cisty_prijem_kc"] is None and "zmena_proti_predchozimu_tydnu_procent" not in f
    assert weekly.fact_lines(f)[0] == "Celkem: 2 ks, čistě 30,00 USD"


def test_vyloucene_se_nepocita(conn):
    db.set_excluded(conn, "cosmos", "b", "zkušební")
    assert facts(conn)["prodano_kusu"] == 1


def test_radky_cisel(conn):
    lines = weekly.fact_lines(facts(conn))
    assert lines[0] == "Celkem: 2 ks, čistě 30,00 USD (≈ 600,00 Kč)"
    assert "Cosmos: 2 ks, ≈ 600,00 Kč" in lines
    assert "Nejprodávanější: Medieval Village" in lines
    assert lines[-1] == "Předchozí týden (12. 1. – 18. 1. 2026): 1 ks, ≈ 300,00 Kč (změna +100 %)"


# --- kontrola čísel (eval: ručně napsané komentáře, dobré i špatné) --------------------------

GOOD = [
    "Minulý týden se prodaly 2 kusy a čistý příjem byl 30,00 USD, tedy asi 600,00 Kč.",
    "Nejlépe šel Medieval Village. Oproti předchozímu týdnu je příjem vyšší o 300,00 Kč, tedy o 100 %.",
    "Cosmos přinesl 600,00 Kč, Fab byl po refundu na nule.",
    "Týden 19. 1. – 25. 1. 2026 byl lepší než předchozí, prodal se o jeden kus víc.",
    "Příjem se zvýšil zhruba o 99 % proti předchozímu týdnu.",  # tolerance 1 bodu u procent
    "Proti 1 kusu v předchozím týdnu se prodaly dva.",
    "Dobrý týden, hlavně díky Cosmosu.",  # bez čísel
]
BAD = [
    ("Minulý týden se prodaly 4 kusy.", ["4"]),  # vymyšlený počet
    ("Čistý příjem byl 35,00 USD.", ["35,00"]),  # vymyšlená částka
    ("Příjem vzrostl o 150 %.", ["150 %"]),  # procento mimo toleranci
    ("Cosmos přinesl 650,00 Kč.", ["650,00"]),  # přehozená / špatná částka
    ("Prodalo se pět kusů.", ["pět"]),  # slovní číslovka
    ("V průměru 10,00 USD za kus.", ["10,00"]),  # dopočítané číslo, které v datech není
    ("Celkem 1 234,50 Kč.", ["1 234,50"]),  # číslo s mezerou v tisících
]


@pytest.mark.parametrize("text", GOOD)
def test_kontrola_propusti_spravna_cisla(conn, text):
    assert weekly.check(text, facts(conn)) == []


@pytest.mark.parametrize(("text", "bad"), BAD)
def test_kontrola_zastavi_vymyslena_cisla(conn, text, bad):
    assert weekly.check(text, facts(conn)) == bad


# --- komentář: pokus, druhý pokus, vzdání ----------------------------------------------------

def test_komentar_projde_napoprve(conn):
    result = weekly.commentary(facts(conn), lambda f, rejected: GOOD[0])
    assert result.text == GOOD[0] and result.note is None


def test_druhy_pokus_dostane_spatna_cisla(conn):
    calls = []

    def writer(f, rejected):
        calls.append(rejected)
        return "Prodaly se 4 kusy." if rejected is None else GOOD[0]

    result = weekly.commentary(facts(conn), writer)
    assert calls == [None, ["4"]]
    assert result.text == GOOD[0]
    assert "neprošel kontrolou čísel ['4']" in result.log[0]


def test_dvakrat_spatne_jen_cisla(conn):
    result = weekly.commentary(facts(conn), lambda f, rejected: "Prodaly se 4 kusy.")
    assert result.text is None
    assert result.note == "Komentář Claude neprošel kontrolou čísel, posílám jen čísla."
    assert len(result.log) == 2


def test_vypadek_api(conn):
    def writer(f, rejected):
        raise weekly.CommentaryError("API Anthropicu není dostupné")

    result = weekly.commentary(facts(conn), writer)
    assert result.text is None and result.note == "Komentář Claude chybí: API Anthropicu není dostupné."


def test_bez_klice():
    with pytest.raises(weekly.CommentaryError, match="ANTHROPIC_API_KEY"):
        weekly.ClaudeWriter("")


# --- volání API (podvržený klient, bez sítě) --------------------------------------------------

class FakeClient:
    def __init__(self, response):
        self.calls = []
        self.response = response
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


def test_pozadavek_na_api(conn):
    client = FakeClient(response(GOOD[0]))
    f = facts(conn)
    assert weekly.ClaudeWriter("", client=client)(f, ["4"]) == GOOD[0]
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"] == {"effort": "low"}
    assert "Používej jen čísla" in call["system"]
    user = call["messages"][0]["content"]
    assert '"prodano_kusu": 2' in user and "čísla, která v datech nejsou: 4" in user


def test_odmitnuti(conn):
    client = FakeClient(response("", stop_reason="refusal"))
    with pytest.raises(weekly.CommentaryError, match="odmítl"):
        weekly.ClaudeWriter("", client=client)(facts(conn))
