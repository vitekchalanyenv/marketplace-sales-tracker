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


# --- kontrola komentáře (eval: ručně napsané komentáře, dobré i špatné) ----------------------
# Data z fixture: Cosmos 2 kusy 600 Kč, Fab 0 kusů, produkt1 = Medieval Village, příjem proti
# předchozímu týdnu vzrostl o 300 Kč (100 %), kusů o 1 víc.

GOOD = [
    "Za týden {obdobi} se prodalo {celkem_kusu} a čistý příjem byl {celkem_kc}.",
    "Příjem proti předchozímu týdnu {smer_prijmu} o {zmena_kc}, tedy o {zmena_procent}.",
    "Z produktů vedl {nejprodavanejsi_produkt}, který přinesl {produkt1_kc}.",
    "Hlavním kanálem byl {nejlepsi_marketplace} s příjmem {cosmos_kc}.",
    "Produkt {produkt1} přinesl {produkt1_kc}.",
    "Cosmos prodal {cosmos_kusu} a Fab {fab_kusu}.",
    "Kusů se prodalo {smer_kusu} než týden předtím, rozdíl je {zmena_kusu}.",
    "Z Cosmosu přišlo {cosmos_kc}. Dobrý týden.",
    "Dobrý týden pro Cosmos.",
]
BAD = [
    # čísla napsaná přímo (i ta, která v datech jsou – i správné číslo může být u špatné věci)
    ("Minulý týden se prodaly 4 kusy.", "číslo napsané přímo: 4"),
    ("Cosmos prodal 1 kus a CGTrader 2 kusy.", "číslo napsané přímo: 1, 2"),
    ("Cosmos vydělal 330,87 Kč.", "číslo napsané přímo: 330,87"),
    ("Prodalo se pět kusů.", "číslovka slovem „pět“"),
    ("Tento týden žádný prodej z Fabu.", "číslovka slovem „žádný“"),
    # vlastní směr změny (pravdivost směru zná jen kód)
    ("Prodeje vzrostly o {zmena_procent}.", "vlastní směr změny „vzrostly“"),
    ("Příjem klesl o {zmena_kc}.", "vlastní směr změny „klesl“"),
    ("Prodalo se víc kusů než minule.", "vlastní směr změny „víc“"),
    ("Byl to lepší týden než ten předtím.", "vlastní směr změny „lepší“"),
    # přehozené hodnoty: značka stojí u jiného marketplace / produktu
    ("Cosmos prodal {fab_kusu} a Fab {cosmos_kusu}.", "{fab_kusu} patří k Fab, ale ve větě stojí u Cosmos"),
    ("Cosmos vydělal {fab_kc}.", "{fab_kc} patří k Fab, ale ve větě stojí u Cosmos"),
    ("{produkt2} vydělal {produkt1_kc}.", "{produkt1_kc} patří k produkt1, ale ve větě stojí u produkt2"),
    ("Celkem přišlo {cosmos_kc}.", "{cosmos_kc} stojí ve větě bez názvu"),
    # množství, pořadí a příčiny slovy (druhé kolo nezávislé kontroly)
    ("Gumroad měl jediný prodej, Cosmos oba zbylé.", "číslovka slovem „jediný“"),
    ("Gumroad měl jediný prodej, Cosmos oba zbylé.", "číslovka slovem „oba“"),
    ("Prodalo se několik kusů, většinou na Gumroadu.", "číslovka slovem „několik“"),
    ("Prodalo se několik kusů, většinou na Gumroadu.", "číslovka slovem „většinou“"),
    ("Prodal se jen pár kusů.", "číslovka slovem „pár“"),
    ("Nejlépe se dařilo na Gumroadu.", "vlastní pořadí „Nejlépe“"),
    ("Gumroad byl nejsilnější kanál.", "vlastní pořadí „nejsilnější“"),
    ("Příjem {smer_prijmu}, hlavně kvůli Gumroadu.", "vlastní příčina „kvůli“"),
    ("Dobrý týden, hlavně díky Cosmosu.", "vlastní příčina „díky“"),
    ("Většinu přinesl produkt Medieval Village.", "název produktu napsaný přímo „Medieval Village“"),
    ("Hlavním kanálem byl {nejlepsi_marketplace} s příjmem {fab_kc}.", "{fab_kc} patří k Fab, ale ve větě stojí u Cosmos"),
    # značka, která neexistuje
    ("Příjem byl {celkem_eur}.", "neznámá značka {celkem_eur}"),
]


def available(conn):
    return weekly.slots(facts(conn))


def test_znacky_z_dat(conn):
    s = available(conn)
    assert s["celkem_kusu"].value == "2 kusy" and s["celkem_kc"].value == "600,00 Kč"
    assert s["smer_prijmu"].value == "vzrostl" and s["zmena_procent"].value == "100 %"
    assert s["smer_kusu"].value == "více" and s["zmena_kusu"].value == "1 kus"
    assert (s["cosmos_kc"].value, s["cosmos_kc"].entity) == ("600,00 Kč", "Cosmos")
    assert s["produkt1"].value == "Medieval Village" and s["produkt1_kusu"].entity == "produkt1"


def test_smer_pri_poklesu(conn):
    db.upsert_sales(conn, [sale("prev-big", 9000, datetime(2026, 1, 15, 9, 0, tzinfo=UTC))])
    s = available(conn)
    assert s["smer_prijmu"].value == "klesl" and s["zmena_kc"].value == "1 500,00 Kč"  # bez znaménka


@pytest.mark.parametrize("text", GOOD)
def test_kontrola_propusti_dobry_komentar(conn, text):
    assert weekly.check(text, available(conn)) == []


@pytest.mark.parametrize(("text", "problem"), BAD)
def test_kontrola_zastavi_spatny_komentar(conn, text, problem):
    problems = weekly.check(text, available(conn))
    assert problem in "; ".join(problems)


def test_dosazeni_hodnot(conn):
    text = "Příjem proti předchozímu týdnu {smer_prijmu} o {zmena_kc}, tedy o {zmena_procent}."
    assert weekly.render(text, available(conn)) == (
        "Příjem proti předchozímu týdnu vzrostl o 300,00 Kč, tedy o 100 %."
    )


# --- komentář: pokus, druhý pokus, vzdání ----------------------------------------------------

def test_komentar_projde_napoprve(conn):
    result = weekly.commentary(facts(conn), lambda s, rejected: GOOD[1])
    assert result.text == "Příjem proti předchozímu týdnu vzrostl o 300,00 Kč, tedy o 100 %."
    assert result.note is None


def test_druhy_pokus_dostane_problemy(conn):
    calls = []

    def writer(s, rejected):
        calls.append(rejected)
        return "Prodaly se 4 kusy." if rejected is None else GOOD[0]

    result = weekly.commentary(facts(conn), writer)
    assert calls[0] is None and calls[1] == ["číslo napsané přímo: 4"]
    assert result.text.startswith("Za týden 19. 1. – 25. 1. 2026 se prodalo 2 kusy")
    assert "pokus 1: komentář neprošel kontrolou (číslo napsané přímo: 4)" in result.log[0]


def test_dvakrat_spatne_jen_cisla(conn):
    result = weekly.commentary(facts(conn), lambda s, rejected: "Cosmos vydělal {fab_kc}.")
    assert result.text is None
    assert result.note == "Komentář Claude neprošel kontrolou čísel, posílám jen čísla."
    assert len(result.log) == 2


def test_vypadek_api(conn):
    def writer(s, rejected):
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
    s = available(conn)
    assert weekly.ClaudeWriter("", client=client)(s, ["číslo napsané přímo: 4"]) == GOOD[0]
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"] == {"effort": "low"}
    assert "Čísla do textu nepíšeš ty" in call["system"]
    user = call["messages"][0]["content"]
    assert '"celkem_kusu": {' in user and '"hodnota": "2 kusy"' in user
    assert "neprošla kontrolou: číslo napsané přímo: 4" in user
    assert "Medieval Village" in user and "sales" not in user  # jen značky, nic jiného z DB


def test_odmitnuti(conn):
    client = FakeClient(response("", stop_reason="refusal"))
    with pytest.raises(weekly.CommentaryError, match="odmítl"):
        weekly.ClaudeWriter("", client=client)(available(conn))
