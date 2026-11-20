"""Společné pomůcky pro testy: načtení vymyšlených vzorků Gumroadu."""

import copy
import json
from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


def load_sample(name: str) -> dict:
    return json.loads((SAMPLE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def page1() -> dict:
    """První stránka odpovědi /v2/sales (3 prodeje, má next_page_key)."""
    return load_sample("gumroad_sales.json")


@pytest.fixture
def page2() -> dict:
    """Druhá (poslední) stránka odpovědi /v2/sales (2 prodeje, bez next_page_key)."""
    return load_sample("gumroad_sales_page2.json")


@pytest.fixture
def all_records(page1, page2) -> list[dict]:
    return copy.deepcopy(page1["sales"] + page2["sales"])
