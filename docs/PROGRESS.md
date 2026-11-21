# Postup

## Hotovo

- 2026-11-20 – M0: kostra repa, pravidla, plán, přehled zdrojů, návrh specifikace M1.
- 2026-11-20 – M1: Gumroad → SQLite. Napsáno, testy prošly (64), **ověřeno na skutečném prodeji** (zkušební nákup
  Vítka přes slevový kód): staženo 1, druhý běh 0 nových, `net` sedí se vzorcem poplatků.
  Na skutečných datech neověřeno: refund, stránkování (>100 prodejů).
- 2026-11-20 – M2: katalog produktů + párování (`catalog check`, `catalog match`, párování po `sync`). Napsáno,
  testy prošly (111), ověřeno na skutečných datech: Vítkův `data/private/katalog.yaml` (5 produktů vč. bundle) je
  bez chyb, jediný skutečný prodej (Gumroad) spárován. Názvy listingů Fab/Cosmos/CGTrader jsou od Vítka a neověřené,
  ukáže je `catalog check` po importu v M3/M4.
- 2026-11-21 – M3: import denního CSV reportu z Fabu (`import fab [soubor]`, bez cesty všechna CSV z
  `data/private/fab/`). Napsáno, testy prošly (157), **ověřeno na skutečném reportu** (1. 10. – 20. 11. 2026):
  součty `Net Sales` / `Net Units` sedí s CSV, druhý import 0 nových, všechny řádky spárovány s katalogem.
  Do modelu přibylo `quantity`.

## Rozpracováno

- (nic)

## Čeká na Vítka

- (M4) Volitelně požádat o CGTrader API.

## Otevřené otázky

- Měny napříč marketplaces: do jaké měny převádět pro týdenní shrnutí (USD? CZK, protože výplaty z Gumroadu jdou v CZK?)
  a odkud brát kurzy (např. ČNB)? Rozhodnout před milníkem se shrnutím.

## Známé problémy

- V DB je zkušební prodej Gumroad (malá částka, 2026-11-20). Zkreslí součty, dokud se nevyřeší (refund / označení jako test).
- HTTPS na Vítkově počítači jde přes certifikát, kterému věří jen úložiště Windows (antivirus/proxy). Řešeno: git → `http.sslBackend schannel`, Python → `ssl.create_default_context()`. Každý nový HTTP klient musí jet stejně.
  `uv add` potřebuje `--system-certs`.

## Rozhodnutí

- 2026-11-21 – Fab: refund = samostatný záporný záznam (`refunded`); `net = 88 % Net Sales`; `Day` v Europe/Prague;
  měna USD; společný model má `quantity`.
- 2026-11-20 – Katalog: produkt = 1 listing na marketplace (verze se neprodávají zvlášť); Fab bundle = samostatný produkt.
- 2026-11-20 – Párování jen přesně (ID, pak normalizovaný název); podobnost jen jako návrh.
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
