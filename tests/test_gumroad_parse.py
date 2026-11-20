"""Převod záznamu z Gumroad /v2/sales na společný model prodeje (spec M1, Mapování)."""

from datetime import UTC, datetime

import pytest

from sales_tracker.gumroad import SkipRecord, parse_sale
from sales_tracker.models import Status


def by_order(records, order_id):
    return next(r for r in records if r["order_id"] == order_id)


def test_bezny_prodej_se_prevede_na_spolecny_model(all_records):
    record = by_order(all_records, 900001)
    sale = parse_sale(record)

    assert sale.marketplace == "gumroad"
    assert sale.external_id == "SAMPLE-aaaaaaaaaaaaaaaaaaaa=="
    assert sale.product_title == "Sample Medieval Village Environment"
    assert sale.product_ref == "SAMPLE-prod-medieval-village=="
    assert sale.sold_at == datetime(2026, 10, 20, 12, 15, tzinfo=UTC)
    assert sale.gross_cents == 1499
    assert sale.net_cents == 1499 - 273  # price − gumroad_fee
    assert sale.currency == "USD"
    assert sale.status is Status.SOLD
    assert sale.raw == record


def test_castky_jsou_cela_cisla_ne_float(all_records):
    for record in all_records:
        sale = parse_sale(record)
        assert type(sale.gross_cents) is int
        assert type(sale.net_cents) is int


def test_prodej_pres_discover_odecte_30_procent(all_records):
    sale = parse_sale(by_order(all_records, 900002))
    assert sale.gross_cents == 2999
    assert sale.net_cents == 2999 - 900


def test_prodej_zdarma(all_records):
    sale = parse_sale(by_order(all_records, 900005))
    assert sale.gross_cents == 0
    assert sale.net_cents == 0


def test_platba_v_mene_kupujiciho_se_ulozi_v_usd(all_records):
    """buyer_presentment (EUR) není příjem prodejce, částky se berou z price/gumroad_fee v USD."""
    sale = parse_sale(by_order(all_records, 900004))
    assert sale.currency == "USD"
    assert sale.gross_cents == 2999
    assert sale.net_cents == 2999 - 467


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, Status.SOLD),
        ({"partially_refunded": True}, Status.PARTIALLY_REFUNDED),
        ({"refunded": True}, Status.REFUNDED),
        ({"refunded": True, "partially_refunded": True}, Status.REFUNDED),
        ({"chargedback": True, "refunded": True}, Status.CHARGEBACK),
    ],
)
def test_stav_prodeje(all_records, flags, expected):
    record = by_order(all_records, 900001)
    for key in ("refunded", "partially_refunded", "chargedback"):
        record.pop(key, None)  # chybějící pole = false
    record.update(flags)
    assert parse_sale(record).status is expected


def test_stav_ze_vzorku(all_records):
    assert parse_sale(by_order(all_records, 900002)).status is Status.PARTIALLY_REFUNDED
    assert parse_sale(by_order(all_records, 900003)).status is Status.REFUNDED


def test_chybejici_volitelna_pole_nevadi(all_records):
    """Gumroad pole s hodnotou null vůbec neposílá (Purchase#as_json, delete_if nil)."""
    record = by_order(all_records, 900003)
    assert "tax_cents" not in record and "affiliate" not in record
    assert parse_sale(record).external_id == "SAMPLE-cccccccccccccccccccc=="


def test_bez_poplatku_je_cisty_prijem_neznamy(all_records):
    record = by_order(all_records, 900001)
    del record["gumroad_fee"]
    assert parse_sale(record).net_cents is None


def test_cas_s_jinou_zonou_se_prevede_na_utc(all_records):
    record = by_order(all_records, 900001)
    record["created_at"] = "2026-10-20T14:15:00+02:00"
    assert parse_sale(record).sold_at == datetime(2026, 10, 20, 12, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("change", "reason_part"),
    [
        ({"id": None}, "id"),
        ({"id": ""}, "id"),
        ({"created_at": None}, "created_at"),
        ({"created_at": "včera"}, "created_at"),
        ({"created_at": "2026-10-20T12:15:00"}, "created_at"),  # bez časové zóny
        ({"price": None}, "price"),
        ({"price": "14.99"}, "price"),
        ({"price": 14.99}, "price"),  # float nebrat
        ({"price": True}, "price"),
        ({"price": -100}, "price"),
        ({"gumroad_fee": 2.5}, "gumroad_fee"),
    ],
)
def test_vadny_zaznam_se_preskoci_s_duvodem(all_records, change, reason_part):
    record = by_order(all_records, 900001)
    for key, value in change.items():
        if value is None:
            record.pop(key)
        else:
            record[key] = value

    with pytest.raises(SkipRecord) as exc:
        parse_sale(record)
    assert reason_part in exc.value.reason


def test_duvod_preskoceni_neobsahuje_osobni_udaje(all_records):
    record = by_order(all_records, 900001)
    del record["created_at"]
    with pytest.raises(SkipRecord) as exc:
        parse_sale(record)
    text = f"{exc.value.external_id} {exc.value.reason}"
    assert "@" not in text
    assert exc.value.external_id == "SAMPLE-aaaaaaaaaaaaaaaaaaaa=="
