"""Katalog produktů: načtení, validace a párování (spec M2)."""

import textwrap
from pathlib import Path

import pytest

from sales_tracker.catalog import CatalogError, load_catalog

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample" / "katalog.yaml"


def write(tmp_path, text: str) -> Path:
    path = tmp_path / "katalog.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def errors_of(tmp_path, text: str) -> str:
    with pytest.raises(CatalogError) as exc:
        load_catalog(write(tmp_path, text))
    return "\n".join(exc.value.errors)


# --- načtení -----------------------------------------------------------------------------------


def test_vzorovy_katalog_se_nacte():
    catalog = load_catalog(SAMPLE)
    assert [p.key for p in catalog.products] == ["medieval-village", "scifi-hangar"]
    assert catalog.name_of("scifi-hangar") == "Sci-Fi Hangar Environment"


def test_ciselny_ref_se_bere_jako_text(tmp_path):
    """CGTrader může mít číselná ID; YAML je načte jako int."""
    catalog = load_catalog(
        write(
            tmp_path,
            """
            products:
              - key: kitbash
                name: Kitbash
                listings:
                  cgtrader:
                    - ref: 123456
            """,
        )
    )
    assert catalog.match("cgtrader", "123456", None) == "kitbash"


# --- párování ----------------------------------------------------------------------------------


@pytest.fixture
def catalog():
    return load_catalog(SAMPLE)


def test_parovani_podle_ref(catalog):
    assert catalog.match("gumroad", "SAMPLE-prod-scifi-hangar==", "cokoli") == "scifi-hangar"


def test_parovani_podle_nazvu(catalog):
    assert catalog.match("fab", None, "Medieval Village Environment - UE5") == "medieval-village"


def test_nazev_bez_ohledu_na_velikost_pismen_a_mezery(catalog):
    assert catalog.match("fab", None, "  medieval   VILLAGE environment - ue5 ") == "medieval-village"


def test_druhy_listing_na_stejnem_marketplace(catalog):
    assert catalog.match("fab", None, "Medieval Village (old listing)") == "medieval-village"


def test_ref_ma_prednost_pred_nazvem(tmp_path):
    catalog = load_catalog(
        write(
            tmp_path,
            """
            products:
              - key: a
                name: A
                listings: {cosmos: [{ref: slug-a}]}
              - key: b
                name: B
                listings: {cosmos: [{title: "Title B"}]}
            """,
        )
    )
    assert catalog.match("cosmos", "slug-a", "Title B") == "a"
    assert catalog.match("cosmos", "jiny-slug", "Title B") == "b"


def test_nespárovany_prodej(catalog):
    assert catalog.match("fab", None, "Neznámý produkt") is None
    assert catalog.match("gumroad", "neznamy-ref", None) is None
    assert catalog.match("cgtrader", None, None) is None


def test_jiny_marketplace_se_nesparuje(catalog):
    """Stejný název na Gumroadu se nespáruje s listingem z Fabu."""
    assert catalog.match("gumroad", None, "Medieval Village Environment - UE5") is None


def test_podobnost_neparuje_jen_navrhuje(catalog):
    assert catalog.match("fab", None, "Medieval Village Environment UE5") is None
    assert catalog.suggest("Medieval Village Environment UE5") == "medieval-village"
    assert catalog.suggest("Úplně jiná věc") is None
    assert catalog.suggest(None) is None


# --- validace ----------------------------------------------------------------------------------


def test_chybejici_soubor(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_catalog(tmp_path / "neni.yaml")


def test_neplatne_yaml_hlasi_radek(tmp_path):
    errors = errors_of(tmp_path, "products:\n  - key: a\n   name: [neuzavřené\n")
    assert "řádek" in errors


@pytest.mark.parametrize(
    "text",
    ["", "products: 5", "- jen seznam", "produkty: []"],
)
def test_spatna_struktura(tmp_path, text):
    assert "products" in errors_of(tmp_path, text)


def test_chybi_key_a_name(tmp_path):
    errors = errors_of(
        tmp_path,
        """
        products:
          - listings:
              fab:
                - title: X
        """,
    )
    assert "key" in errors and "name" in errors


@pytest.mark.parametrize("key", ["Velka", "s mezerou", "-zacatek", "konec-", "dvě--pomlčky", "ř"])
def test_spatny_tvar_key(tmp_path, key):
    errors = errors_of(
        tmp_path,
        f"""
        products:
          - key: "{key}"
            name: X
            listings:
              fab:
                - title: X
        """,
    )
    assert "key" in errors


def test_duplicitni_key(tmp_path):
    errors = errors_of(
        tmp_path,
        """
        products:
          - key: a
            name: A
            listings: {fab: [{title: A}]}
          - key: a
            name: B
            listings: {fab: [{title: B}]}
        """,
    )
    assert "'a'" in errors and "dvakrát" in errors


def test_neznamy_marketplace(tmp_path):
    errors = errors_of(
        tmp_path,
        """
        products:
          - key: a
            name: A
            listings: {gumraod: [{ref: x}]}
        """,
    )
    assert "gumraod" in errors


@pytest.mark.parametrize(
    "listing", ["{}", "{tittle: X}", "{ref: ''}", "{title: true}", "X", "[]"]
)
def test_spatny_listing(tmp_path, listing):
    errors = errors_of(
        tmp_path,
        f"""
        products:
          - key: a
            name: A
            listings: {{fab: [{listing}]}}
        """,
    )
    assert "'a'" in errors  # chyba je u správného produktu


def test_stejny_nazev_u_dvou_produktu(tmp_path):
    errors = errors_of(
        tmp_path,
        """
        products:
          - key: a
            name: A
            listings: {fab: [{title: "Same Name"}]}
          - key: b
            name: B
            listings: {fab: [{title: "  same   name "}]}
        """,
    )
    assert "'a'" in errors and "'b'" in errors


def test_stejny_ref_u_dvou_produktu(tmp_path):
    errors = errors_of(
        tmp_path,
        """
        products:
          - key: a
            name: A
            listings: {cosmos: [{ref: slug}]}
          - key: b
            name: B
            listings: {cosmos: [{ref: slug}]}
        """,
    )
    assert "slug" in errors


def test_stejny_nazev_na_ruznych_marketplaces_je_ok(tmp_path):
    catalog = load_catalog(
        write(
            tmp_path,
            """
            products:
              - key: a
                name: A
                listings: {fab: [{title: X}], cosmos: [{title: X}]}
            """,
        )
    )
    assert catalog.match("cosmos", None, "X") == "a"


def test_vsechny_chyby_najednou(tmp_path):
    with pytest.raises(CatalogError) as exc:
        load_catalog(
            write(
                tmp_path,
                """
                products:
                  - key: A
                    name: A
                    listings: {fab: [{title: X}]}
                  - key: b
                    listings: {fab: [{title: Y}]}
                """,
            )
        )
    assert len(exc.value.errors) >= 2
