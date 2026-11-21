"""Import denního reportu z Fabu (spec M3). Vše na vymyšlených datech data/sample/fab_report.csv."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_tracker.fab import FabFormatError, parse_report
from sales_tracker.models import Status

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample" / "fab_report.csv"
HEADER = "Day,Source,Listing Title,License,Base Price,Total VAT,Total Tax,Net Units,Net Sales"
GOOD = "2026-01-03,Fab,Sample Listing,Personal,19.99,0.0,0.0,1,19.99"


def write(tmp_path, *lines, name="report.csv", newline="\r\n", bom=False) -> Path:
    path = tmp_path / name
    data = newline.join(lines) + newline
    path.write_bytes(("﻿" if bom else "").encode("utf-8") + data.encode("utf-8"))
    return path


def by_id(report):
    return {s.external_id: s for s in report.sales}


# --- převod řádku ------------------------------------------------------------------------------


def test_vzorovy_report():
    report = parse_report(SAMPLE)
    assert len(report.sales) == 6
    assert report.skipped == [] and report.warnings == []

    sale = by_id(report)["2026-01-03|Fab|Medieval Village Environment - UE5|Personal|1999"]
    assert sale.marketplace == "fab"
    assert sale.product_title == "Medieval Village Environment - UE5"
    assert sale.product_ref is None
    assert sale.gross_cents == 1999
    assert sale.net_cents == 1759  # 1999 × 0,88 = 1759,12
    assert sale.quantity == 1
    assert sale.currency == "USD"
    assert sale.status is Status.SOLD
    assert sale.raw["Listing Title"] == "Medieval Village Environment - UE5"
    assert sale.raw["_file"] == "fab_report.csv"


def test_den_je_v_ceske_zone_zima_i_leto(tmp_path):
    report = parse_report(
        write(
            tmp_path,
            HEADER,
            "2026-01-03,Fab,Winter,Personal,1.0,0.0,0.0,1,1.0",
            "2026-07-01,Fab,Summer,Personal,1.0,0.0,0.0,1,1.0",
        )
    )
    times = {s.product_title: s.sold_at for s in report.sales}
    assert times["Winter"] == datetime(2026, 1, 2, 23, 0, tzinfo=UTC)  # CET = UTC+1
    assert times["Summer"] == datetime(2026, 6, 30, 22, 0, tzinfo=UTC)  # CEST = UTC+2


def test_vice_kusu(tmp_path):
    sale = parse_report(SAMPLE).sales[1]
    assert (sale.quantity, sale.gross_cents, sale.net_cents) == (2, 1900, 1672)


def test_stejny_den_listing_licence_jina_cena_jsou_dva_zaznamy():
    ids = [s.external_id for s in parse_report(SAMPLE).sales]
    assert "2026-01-05|Fab|Sci-Fi Hangar Environment|Personal|950" in ids
    assert "2026-01-05|Fab|Sci-Fi Hangar Environment|Personal|1900" in ids


def test_refund_je_zaporny_zaznam():
    sale = by_id(parse_report(SAMPLE))["2026-01-09|Fab|Medieval Village Environment - UE5|Personal|1999"]
    assert sale.status is Status.REFUNDED
    assert (sale.quantity, sale.gross_cents, sale.net_cents) == (-1, -1999, -1759)


@pytest.mark.parametrize(
    ("text", "cents"),
    [("7.5", 750), ("12.0", 1200), ("12", 1200), ("0.01", 1), ("19.99", 1999), ("-29.99", -2999)],
)
def test_castky_na_centy(tmp_path, text, cents):
    row = f"2026-01-03,Fab,X,Personal,{text.lstrip('-')},0.0,0.0,{-1 if text.startswith('-') else 1},{text}"
    sale = parse_report(write(tmp_path, HEADER, row)).sales[0]
    assert sale.gross_cents == cents
    assert type(sale.gross_cents) is int


@pytest.mark.parametrize(("gross", "net"), [(1999, 1759), (500, 440), (1, 1), (3, 3), (25, 22)])
def test_cisty_prijem_88_procent_zaokrouhleni(tmp_path, gross, net):
    """25 × 0,88 = 22,0; 3 × 0,88 = 2,64 → 3; 1 × 0,88 = 0,88 → 1."""
    price = f"{gross // 100}.{gross % 100:02d}"
    sale = parse_report(write(tmp_path, HEADER, f"2026-01-03,Fab,X,Personal,{price},0,0,1,{price}")).sales[0]
    assert sale.net_cents == net


def test_bom_a_lf_se_nactou_stejne(tmp_path):
    a = parse_report(write(tmp_path, HEADER, GOOD, name="a.csv"))
    b = parse_report(write(tmp_path, HEADER, GOOD, name="b.csv", newline="\n", bom=True))
    assert [s.external_id for s in a.sales] == [s.external_id for s in b.sales]


def test_nazev_s_carkou_v_uvozovkach(tmp_path):
    row = '2026-01-03,Fab,"Bundle – A, B, C",Personal,9.0,0,0,1,9.0'
    assert parse_report(write(tmp_path, HEADER, row)).sales[0].product_title == "Bundle – A, B, C"


# --- validace ----------------------------------------------------------------------------------


def test_spatna_hlavicka_nic_nenacte(tmp_path):
    path = write(tmp_path, HEADER.replace("Net Sales", "Net Revenue") + ",Extra", GOOD)
    with pytest.raises(FabFormatError) as exc:
        parse_report(path)
    message = str(exc.value)
    assert "Net Sales" in message and "Net Revenue" in message and "Extra" in message


def test_prazdny_soubor(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(FabFormatError):
        parse_report(path)


def test_neni_utf8(tmp_path):
    path = tmp_path / "cp1250.csv"
    path.write_bytes((HEADER + "\r\n2026-01-03,Fab,Kůň,Personal,1,0,0,1,1\r\n").encode("cp1250"))
    with pytest.raises(FabFormatError) as exc:
        parse_report(path)
    assert "UTF-8" in str(exc.value)


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("03.01.2026,Fab,X,Personal,1.0,0,0,1,1.0", "Day"),
        ("2026-02-30,Fab,X,Personal,1.0,0,0,1,1.0", "Day"),
        ("2026-01-03,Fab,X,Personal,1,5,0,0,1,1.0", "sloupc"),  # čárka v ceně → 10 sloupců
        ("2026-01-03,Fab,X,Personal,abc,0,0,1,1.0", "Base Price"),
        ("2026-01-03,Fab,X,Personal,1.999,0,0,1,1.999", "Base Price"),
        ("2026-01-03,Fab,X,Personal,1.0,0,0,1.5,1.5", "Net Units"),
        ("2026-01-03,Fab,X,Personal,1.0,0,0,1,", "Net Sales"),
        ("2026-01-03,Fab,,Personal,1.0,0,0,1,1.0", "Listing Title"),
        ("2026-01-03,Fab,X,,1.0,0,0,1,1.0", "License"),
        ("2026-01-03,,X,Personal,1.0,0,0,1,1.0", "Source"),
    ],
)
def test_vadny_radek_se_preskoci_s_cislem_radku(tmp_path, row, reason):
    report = parse_report(write(tmp_path, HEADER, GOOD, row))
    assert len(report.sales) == 1
    assert len(report.skipped) == 1
    skipped = report.skipped[0]
    assert skipped.line == 3
    assert reason in skipped.reason


def test_nesedi_soucin_jen_upozorni(tmp_path):
    report = parse_report(write(tmp_path, HEADER, "2026-01-03,Fab,X,Personal,10.0,0,0,2,15.0"))
    assert report.sales[0].gross_cents == 1500  # bereme Net Sales
    assert len(report.warnings) == 1 and "řádek 2" in report.warnings[0]


def test_duplicitni_klic_v_souboru_preskoci_oba(tmp_path):
    report = parse_report(write(tmp_path, HEADER, GOOD, GOOD, "2026-01-04,Fab,Y,Personal,1,0,0,1,1"))
    assert [s.product_title for s in report.sales] == ["Y"]
    assert sorted(s.line for s in report.skipped) == [2, 3]
    assert all("dvakrát" in s.reason for s in report.skipped)


def test_prazdne_radky_se_ignoruji(tmp_path):
    report = parse_report(write(tmp_path, HEADER, GOOD, "", ""))
    assert len(report.sales) == 1 and report.skipped == []
