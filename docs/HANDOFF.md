# Předání

**Relace:** 2026-11-20 až 2026-11-21 (M1 dokončeno, M2, M3)

## Kde jsme

- **M1 Gumroad ✅** – ověřeno na skutečném (zkušebním) prodeji Vítka: struktura odpovědi i vzorec poplatků sedí.
  Neověřeno na skutečných datech: refund, stránkování (>100 prodejů).
- **M2 Katalog ✅** – `data/private/katalog.yaml` (5 produktů vč. Fab bundle), `catalog check` / `catalog match`,
  párování po každém `sync` / `import`. Jen přesné párování (ID, pak normalizovaný název), podobnost = návrh.
- **M3 Fab ✅** – `import fab [soubor]` (bez cesty všechna CSV z `data/private/fab/`), ověřeno na skutečném reportu
  1. 10. – 20. 11. 2026: součty sedí s CSV, opakovaný import 0 nových, vše spárováno.
- DB `data/private/sales.db`: všechny záznamy spárované. Model má `status` a `quantity`.
- Testy: **157 passed**, `ruff check` čistý (2026-11-21).
- Kód: `src/sales_tracker/` – `models.py`, `db.py` (migrace sloupců), `gumroad.py`, `fab.py`, `catalog.py`, `cli.py`.

## Co udělat dál

1. **M4 – Cosmos + CGTrader.** Než se cokoli automatizuje v prohlížeči, zeptat se Vítka (pravidlo 7).
   - Cosmos: jen webová tabulka (Reports → Sales, 10 / stránka), bez exportu. Možnosti: ruční kopie tabulky do souboru,
     nebo zjistit, jestli web volá vlastní JSON API (jen s Vítkovým souhlasem, šetrně).
   - CGTrader: zjistit, jestli Vítek má / chce API přístup; jinak export / ruční kopie z My Sales.
2. Vyřešit zkušební prodej z Gumroadu v DB (refund na Gumroadu → ověří i refund, nebo označit jako test).

## Otevřené otázky pro Vítka

- M4: jak číst Cosmos a CGTrader (viz výše).
- Měny pro týdenní shrnutí (USD, nebo CZK?) a zdroj kurzů – před M5.

## Pozor

- HTTPS jen přes úložiště certifikátů Windows: Python `ssl.create_default_context()`, git `schannel`,
  `uv add --system-certs`.
- Do veřejného repa (spec, ZDROJE) **jen formát a vymyšlené příklady**, nikdy skutečné řádky reportů.
- Testy nikdy nesahají na `data/private/` (cesty předávat do `tmp_path`).
- `.env` načítat explicitní cestou z cwd.
- V heredocu s Pythonem pozor na `\n` / `\b` v řetězcích (dvakrát rozbilo soubor) – na víceřádkové úpravy kódu
  raději nástroj Edit.

## Jak pracovat

- `/navazani` na začátku, `/predani` na konci.
