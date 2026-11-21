# Předání

**Relace:** 2026-11-21 (M4: průzkum Cosmos + CGTrader, agent pro Cosmos)

## Kde jsme

- **M1 Gumroad ✅, M2 Katalog ✅, M3 Fab ✅** (viz `docs/PROGRESS.md`).
- **M4a Cosmos – agent v prohlížeči hotový:** `sync cosmos` (Playwright + nainstalovaný Chrome, vlastní profil
  `data/private/browser/cosmos/`, headless). Zachytí JSON, který si stránka Sales sama načte z
  `api.publisher.leartesstudios.com/sales`; token ani heslo neprochází kódem. Ověřeno na skutečném účtu:
  všechny transakce, tržba i payout sedí na cent, druhý běh 0 nových a zastaví na 1. stránce.
  - Jádro `src/sales_tracker/cosmos.py` (validace, dělení payoutu podle zaplacených částek, stránkování),
    tenká vrstva `cosmos_browser.py`, pokus `spikes/cosmos_playwright.py`.
  - Přihlášení: `sync cosmos --login` (Vítek sám, reCAPTCHA).
- **M4b CGTrader:** průzkum hotový (`docs/ZDROJE.md`). Report z My Sales chodí **e-mailem**; Vítek ho nahraje.
  O API požádáno, čeká se.
- DB: všechny záznamy spárované s katalogem.
- Testy **196 passed**, `ruff check` čistý (2026-11-21).

## Co udělat dál

1. **Ruční kopie Cosmosu** (cesta 2): až Vítek uloží `data/private/cosmos/vzorek.txt`, napsat parser `from_paste`
   podle skutečného vzorku; multi-produktové transakce dělit podle `price` z katalogu (katalog `price` ještě neumí).
2. **CGTrader (M4b):** až bude report z e-mailu v `data/private/cgtrader/`, prozkoumat formát a napsat spec + import.
3. **M5 – denní agent** (požadavek Vítka): každý den sám spustí `sync gumroad`, `sync cosmos` a importy nových
   souborů a **dá vědět, když něco selže** (hlavně vypršené přihlášení Cosmosu). Nejdřív spec a otázky:
   jak notifikovat, kdy běžet, co když je počítač vypnutý; souvisí s týdenním shrnutím.

## Otevřené otázky pro Vítka

- M5: kanál upozornění (notifikace Windows / e-mail / jiné), čas běhu.
- Měny pro týdenní shrnutí (USD, nebo CZK?) a zdroj kurzů.
- Refund na Cosmosu: zatím žádný nebyl → formát `refund_details` neznámý (agent ho uloží jako refund a upozorní).

## Pozor

- HTTPS jen přes úložiště certifikátů Windows: Python `ssl.create_default_context()`, git `schannel`,
  `uv add --system-certs`.
- Do veřejného repa (spec, ZDROJE) **jen formát a vymyšlené příklady**, nikdy skutečné řádky, částky ani časy prodejů.
- Testy nikdy nesahají na `data/private/` ani na síť / prohlížeč.
- Na tvrzení „X neexistuje“ (např. API) sledovat celou síť po načtení stránky, ne jen jednu doménu.
- Ruční requesty s Vítkovým tokenem z prohlížeče jsou v tomto prostředí blokované – a správně; Cosmos jen přes
  Playwright profil, kde přihlášení drží prohlížeč.
- V heredocu s Pythonem pozor na `\n` / `\b`; víceřádkové úpravy kódu raději nástrojem Edit.

## Jak pracovat

- `/navazani` na začátku, `/predani` na konci.
