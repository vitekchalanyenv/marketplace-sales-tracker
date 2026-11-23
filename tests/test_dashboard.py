"""Přehled (spec M6): stránka se vykreslí na vymyšlených datech dema, bez prohlížeče a sítě."""

import io
from contextlib import redirect_stdout

import pytest
from streamlit.testing.v1 import AppTest

from sales_tracker import dashboard, demo


@pytest.fixture
def demo_page(tmp_path, monkeypatch):
    with redirect_stdout(io.StringIO()):
        demo.run(work=tmp_path)
    monkeypatch.setenv(dashboard.ENV_DB, str(tmp_path / "sales.db"))
    monkeypatch.setenv(dashboard.ENV_STATE, str(tmp_path / "state.json"))
    monkeypatch.setenv(dashboard.ENV_CATALOG, str(tmp_path / "katalog.yaml"))
    monkeypatch.setenv(dashboard.ENV_DEMO, "1")
    page = AppTest.from_file(str(dashboard.APP), default_timeout=30)
    page.run()
    return page


def test_stranka_se_vykresli_bez_chyby(demo_page):
    assert not demo_page.exception
    assert demo_page.title[0].value == "Přehled prodejů"
    assert [m.label for m in demo_page.metric] == ["Tento měsíc", "Minulý měsíc", "Letos"]
    assert all("Kč" in m.value for m in demo_page.metric)
    assert [h.value for h in demo_page.subheader][1:] == [
        "Produkty napříč platformami", "Posledních 20 prodejů", "Stav zdrojů",
    ]
    assert not demo_page.warning  # demo kurzy jsou vždy k dispozici


def test_filtr_marketplace(demo_page):
    demo_page.multiselect[0].set_value(["fab"]).run()
    assert not demo_page.exception
    recent = demo_page.dataframe[2].value
    assert set(recent["Marketplace"]) == {"Fab"}


def test_vlastni_rozsah_bez_prodeju(demo_page):
    from datetime import date

    demo_page.selectbox[0].set_value("Vlastní rozsah").run()
    demo_page.date_input[0].set_value((date(2020, 1, 1), date(2020, 1, 31))).run()
    assert not demo_page.exception
    assert any("žádné prodeje" in m.value for m in demo_page.markdown)


def test_streamlit_jen_lokalne_a_bez_statistik():
    args = dashboard.command()
    assert args[args.index("--server.address") + 1] == "127.0.0.1"
    assert args[args.index("--browser.gatherUsageStats") + 1] == "false"
