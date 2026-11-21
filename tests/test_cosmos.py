"""Cosmos: převod transakcí z API, dělení payoutu a stránkování (spec M4a). Bez sítě a bez prohlížeče."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_tracker.cosmos import (
    FetchError,
    SkipTransaction,
    fetch_pages,
    from_api,
    split_cents,
    to_sales,
)
from sales_tracker.models import Status

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
NOW = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def pages():
    return {
        n: json.loads((SAMPLE_DIR / f"cosmos_api_page{n}.json").read_text(encoding="utf-8"))
        for n in (1, 2)
    }


def tx_record(pages, tx_id):
    for page in pages.values():
        for record in page["data"]:
            if record["id"] == tx_id:
                return copy.deepcopy(record)
    raise KeyError(tx_id)


# --- split_cents -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "weights", "expected"),
    [
        (5213, [3992, 2000], [3473, 1740]),
        (100, [1, 1, 1], [34, 33, 33]),
        (0, [5, 5], [0, 0]),
        (7, [0, 0], [4, 3]),  # nulové váhy → rovným dílem
        (999, [1], [999]),
    ],
)
def test_split_cents_soucet_sedi_na_cent(total, weights, expected):
    parts = split_cents(total, weights)
    assert parts == expected
    assert sum(parts) == total


# --- from_api + to_sales -----------------------------------------------------------------------


def test_bezna_transakce(pages):
    tx = from_api(tx_record(pages, 20005))
    assert tx.id == "20005"
    assert tx.created_at == datetime(2026, 1, 20, 10, 0, tzinfo=UTC)
    assert tx.amount_cents == 1999 and tx.payout_cents == 1740
    assert not tx.virtual and not tx.refunded

    [sale] = to_sales(tx)
    assert sale.marketplace == "cosmos"
    assert sale.external_id == "20005|sample-medieval-village"
    assert sale.product_ref == "sample-medieval-village"
    assert sale.product_title == "Medieval Village Environment"
    assert sale.sold_at == datetime(2026, 1, 20, 10, 0, tzinfo=UTC)
    assert (sale.quantity, sale.gross_cents, sale.net_cents) == (1, 1999, 1740)
    assert sale.currency == "USD" and sale.status is Status.SOLD
    assert sale.raw["transaction"]["id"] == 20005
    assert sale.raw["source"] == "browser" and sale.raw["item_index"] == 0


def test_vice_produktu_payout_podle_castek(pages):
    sales = to_sales(from_api(tx_record(pages, 20004)))
    assert [s.external_id for s in sales] == ["20004|sample-medieval-village", "20004|sample-scifi-hangar"]
    assert [s.gross_cents for s in sales] == [3992, 2000]
    assert [s.net_cents for s in sales] == [3473, 1740]
    assert sum(s.net_cents for s in sales) == 5213
    assert all(type(s.gross_cents) is int and type(s.net_cents) is int for s in sales)
    assert sales[0].raw["transaction"]["items"][0]["license"] == "studio"


def test_virtual_credits_cela_castka_jako_payout(pages):
    tx = from_api(tx_record(pages, 20003))
    assert tx.virtual and tx.payout_cents is None and tx.amount_cents == 1250
    [sale] = to_sales(tx)
    assert (sale.gross_cents, sale.net_cents, sale.currency) == (1250, 1250, "USD")


def test_refund(pages):
    tx = from_api(tx_record(pages, 20002))
    assert tx.refunded
    assert to_sales(tx)[0].status is Status.REFUNDED


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda r: r.pop("id"), "id"),
        (lambda r: r.pop("created_at"), "created_at"),
        (lambda r: r.update(created_at="včera"), "created_at"),
        (lambda r: r.update(created_at="2026-01-20T10:00:00"), "created_at"),  # bez zóny
        (lambda r: r.update(items=[]), "items"),
        (lambda r: r.update(type="gift"), "type"),
        (lambda r: r.update(payout=None), "payout"),
        (lambda r: r.update(payout={"amount": "17.40", "currency": "EUR"}), "payout"),
        (lambda r: r.update(raw_amount="19.9950"), "raw_amount"),
        (lambda r: r.update(raw_amount="abc"), "raw_amount"),
        (lambda r: r["items"][0].update(amount="18.0000"), "součet"),
        (lambda r: r["items"][0].update(quantity=0), "quantity"),
        (lambda r: r["items"][0].pop("sku"), "sku"),
        (lambda r: r["items"].append(copy.deepcopy(r["items"][0])), "dvakrát"),
    ],
)
def test_vadna_transakce_se_preskoci_s_duvodem(pages, change, reason):
    record = tx_record(pages, 20005)
    change(record)
    with pytest.raises(SkipTransaction) as exc:
        from_api(record)
    assert reason in exc.value.reason


def test_duvod_neobsahuje_nic_navic(pages):
    record = tx_record(pages, 20005)
    record["payout"] = None
    with pytest.raises(SkipTransaction) as exc:
        from_api(record)
    assert exc.value.tx_id == "20005"


# --- fetch_pages -------------------------------------------------------------------------------


def make_loader(pages, calls):
    def load(n):
        calls.append(n)
        return copy.deepcopy(pages[n])

    return load


def test_prvni_beh_projde_vsechny_stranky(pages):
    calls, sleeps = [], []
    records = fetch_pages(make_loader(pages, calls), known_ids=set(), now=NOW, sleep=sleeps.append)
    assert calls == [1, 2]
    assert [r["id"] for r in records] == [20005, 20004, 20003, 20002, 20001]
    assert len(sleeps) == 1 and sleeps[0] >= 3


def test_dalsi_beh_skonci_na_znamych_starych(pages):
    """Stránka 1: vše známé, nejstarší transakce 11 dní → v okně refundů, jde se dál.
    Při NOW o 60 dní později už je vše starší než 30 dní → stačí 1. stránka."""
    known = {"20005", "20004", "20003", "20002", "20001"}
    calls = []
    fetch_pages(make_loader(pages, calls), known_ids=known, now=NOW, sleep=lambda s: None)
    assert calls == [1, 2]

    calls = []
    later = datetime(2026, 4, 1, tzinfo=UTC)
    records = fetch_pages(make_loader(pages, calls), known_ids=known, now=later, sleep=lambda s: None)
    assert calls == [1]
    assert len(records) == 3


def test_neznama_transakce_vede_na_dalsi_stranku(pages):
    known = {"20004", "20003", "20002", "20001"}  # 20005 je nová
    calls = []
    fetch_pages(make_loader(pages, calls), known_ids=known, now=datetime(2026, 4, 1, tzinfo=UTC),
                sleep=lambda s: None)
    assert calls == [1, 2]


def test_pojistka_max_stranek(pages):
    endless = copy.deepcopy(pages[1])
    endless["meta"]["lastPage"] = 10_000
    calls = []

    def load(n):
        calls.append(n)
        page = copy.deepcopy(endless)
        page["meta"]["currentPage"] = n
        return page

    with pytest.raises(FetchError):
        fetch_pages(load, known_ids=set(), now=NOW, sleep=lambda s: None, max_pages=5)
    assert calls == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "bad",
    [{}, {"data": {}}, {"data": [], "meta": {}}, {"data": [], "meta": {"currentPage": "1", "lastPage": 1}}, []],
)
def test_neocekavany_tvar_stranky(bad):
    with pytest.raises(FetchError):
        fetch_pages(lambda n: bad, known_ids=set(), now=NOW, sleep=lambda s: None)


def test_spatne_cislo_stranky(pages):
    with pytest.raises(FetchError):
        fetch_pages(lambda n: copy.deepcopy(pages[1]), known_ids=set(), now=NOW, sleep=lambda s: None)
