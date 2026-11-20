# Postup

## Hotovo

- 2026-11-20 – M0: kostra repa, pravidla, plán, přehled zdrojů, návrh specifikace M1.

## Rozpracováno

- M1 – Gumroad: **napsáno, testy prošly (64), ověřeno na skutečném účtu jen částečně** (2026-11-20):
  - `uv run python -m sales_tracker sync gumroad` proběhl proti skutečnému API: staženo 0 (na Gumroadu zatím není prodej),
    druhý běh i `--since 2020-01-01` OK, neplatný token → správná hláška.
  - Převod prodeje, refundy, stránkování a idempotence ověřeny **jen na vymyšlených datech** (struktura z dokumentace
    a zdrojového kódu Gumroadu).
  - Kritérium hotovosti „stáhne skutečné prodeje“ zůstává otevřené do prvního skutečného prodeje (nebo testovacího
    nákupu přes 100% slevový kód). Pak porovnat odpověď se `ZDROJE.md` a uložit vzorek do `data/private/`.

## Čeká na Vítka

- (M3) Poslat všechny názvy sloupců Fab CSV reportu.
- (M4) Volitelně požádat o CGTrader API.

## Otevřené otázky

- Měny napříč marketplaces: do jaké měny převádět pro týdenní shrnutí (USD? CZK, protože výplaty z Gumroadu jdou v CZK?)
  a odkud brát kurzy (např. ČNB)? Rozhodnout před milníkem se shrnutím.

## Známé problémy

- HTTPS na Vítkově počítači jde přes certifikát, kterému věří jen úložiště Windows (antivirus/proxy). Řešeno: git → `http.sslBackend schannel`, Python → `ssl.create_default_context()`. Každý nový HTTP klient musí jet stejně.

## Rozhodnutí

- 2026-11-20 – Společný model má pole `status` (sold / refunded / partially_refunded / chargeback); refundy u všech marketplaces.
- 2026-11-20 – Gumroad sync bez `--since` stahuje posledních 30 dní (kvůli refundům).
- 2026-11-20 – Gumroad `net_cents = price − gumroad_fee` (fee obsahuje i processing; ověřeno v kódu Gumroadu).
- 2026-11-20 – Částky se ukládají v původní měně marketplace, bez převodu.
- 2026-11-20 – Struktura prodeje z Gumroadu se bere z dokumentace / zdrojového kódu; ověří se na prvním skutečném prodeji.
- 2026-11-20 – Cosmos `Date` je v místním čase Vítka (Europe/Prague, CET/CEST). Při importu převádět do UTC.

## Prostředí (poznámky)

- `git` používá `http.sslBackend schannel` (globálně nastavil Vítek 2026-11-20); s výchozím `openssl` padá na
  „unable to get local issuer certificate“.
- `uv` je v `%USERPROFILE%\.local\bin`, v uživatelském PATH je (2026-11-20). Terminál otevřený dřív ho nevidí,
  pomůže restart terminálu/aplikace.
