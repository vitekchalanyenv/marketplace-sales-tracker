# Předání

**Relace:** 2026-11-20 (M1 Gumroad)

## Kde jsme

- **M1 – Gumroad: napsáno, testy prošly (64), ruff čistý, ověřeno na skutečném účtu jen částečně.**
  - `uv run python -m sales_tracker sync gumroad [--since YYYY-MM-DD]` → `data/private/sales.db` (SQLite).
  - Ostrý běh proti API: staženo 0, protože na Gumroadu zatím **není žádný prodej**. Neplatný token → správná hláška.
  - Struktura prodeje vzata z dokumentace a **zdrojového kódu Gumroadu** (`github.com/antiwork/gumroad`), popsaná
    v `docs/ZDROJE.md`. Převod, refundy, stránkování a idempotence ověřeny jen na vymyšlených datech v `data/sample/`.
- Kód: `src/sales_tracker/` – `models.py` (společný model + `status`), `db.py` (upsert, klíč marketplace + external_id),
  `gumroad.py` (klient + převod), `cli.py`.
- Rozhodnutí této relace jsou v `docs/PROGRESS.md` (sekce Rozhodnutí): `status` v modelu, okno 30 dní,
  `net = price − gumroad_fee`, částky v původní měně, Cosmos čas = Europe/Prague.
- `docs/AI_CHYBY.md`: 2 záznamy (od oka vymyšlené poplatky ve vzorku; `httpx` bez úložiště certifikátů Windows).

## Co udělat dál

1. Uzavřít M1, až bude na Gumroadu první prodej (nebo testovací nákup přes 100% slevový kód – dělá Vítek):
   spustit sync, porovnat skutečnou odpověď se `ZDROJE.md`, uložit vzorek do `data/private/`, případně opravit převod.
2. Mezitím lze začít **M2 (katalog produktů)**: nejdřív spec v `docs/spec/`, Vítek schválí.
   Nebo M3 (Fab CSV), až Vítek pošle sloupce reportu.

## Otevřené otázky pro Vítka

- Měny pro týdenní shrnutí: převádět do USD, nebo CZK? Kurzy odkud (ČNB)? Stačí rozhodnout před M5.
- (M3) Všechny sloupce Fab CSV reportu; (M4) volitelně žádost o CGTrader API.

## Pozor

- Každý nový HTTP klient musí používat úložiště certifikátů Windows (`ssl.create_default_context()`), jinak
  `CERTIFICATE_VERIFY_FAILED`. Git už je na `schannel`.
- `python-dotenv`: `.env` načítat explicitní cestou z cwd (`load_dotenv(Path.cwd() / ".env")`), jinak se hledá od
  souboru modulu nahoru a testy by mohly sáhnout na skutečný `.env`.

## Jak pracovat

- `/navazani` na začátku, `/predani` na konci.
