"""Smoke test: prostředí funguje a v repu nejsou skutečná data."""

import subprocess

import sales_tracker


def test_balicek_jde_importovat():
    assert sales_tracker.__version__ == "0.1.0"


def test_v_gitu_nejsou_skutecna_data():
    """Pojistka: v gitu nesmí být nic z data/private, .env ani databáze."""
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    zakazane = [
        f for f in tracked
        if f.startswith("data/private/") or f == ".env" or f.endswith((".db", ".sqlite"))
    ]
    assert zakazane == [], f"Skutečná data v gitu: {zakazane}"
