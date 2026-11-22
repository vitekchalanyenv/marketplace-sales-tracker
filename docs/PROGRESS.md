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

- M4a – Cosmos: **agent v prohlížeči hotový** – `sync cosmos` (Playwright, vlastní profil, headless, zachytí JSON
  z API stránky). Napsáno, testy prošly (196), **ověřeno na skutečném účtu** 2026-11-21: všechny transakce,
  tržba i payout sedí na cent, druhý běh 0 nových (zastaví na 1. stránce), vše spárováno.
  **Ruční kopie** (`import cosmos`, záložní cesta): napsáno, testy prošly (264), **ověřeno na skutečném vzorku**
  2026-11-22: všechny transakce stejné jako z API (čas na minutu, částky na cent); jediný rozdíl je odhad dělení
  u transakce se dvěma produkty (±2 ¢, součet přesný). Data z agenta ruční kopie nepřepíše (ověřeno: všechny „už v DB“).
  Zbývá: refund (formát `refund_details` neznámý), jak dlouho vydrží přihlášení.
- M5 – denní agent: `run daily` (Gumroad, Cosmos, Fab; každý krok zvlášť, log v `data/private/logs/`)
  a úloha v Plánovači (`scripts/install_task.ps1`, denně 8:00, po zapnutí doběhne zmeškaný běh).
  **Ranní souhrn e-mailem přes Resend, každý den** (nové prodeje po kusech, refundy, součty za měsíc, stav zdrojů).
  Napsáno, testy prošly (222). Na skutečných datech ověřeno: `run daily --dry-run` (měsíční součty sedí s DB)
  a běh přes Plánovač bez okna konzole (ještě ve verzi s notifikací). **Ostré odeslání 2026-11-22:** Resend
  e-mail přijal (bez vlastní domény, odesílatel `onboarding@resend.dev`), stav souhrnu se uložil a Vítek
  potvrdil, že e-mail dorazil do schránky. Neověřeno: chyba při vypršeném přihlášení, doběhnutí po zapnutí PC.
  Notifikace ve Windows (první verze) nepřišla, nahrazena e-mailem. Týdenní shrnutí zbývá.
- M4b – CGTrader: `import cgtrader [soubor]` (CSV report z e-mailu, bez kupujícího a země). Napsáno, testy prošly
  (238), **ověřeno na skutečném reportu** 2026-11-22: částky sedí s CSV, druhý import 0 nových,
  spárováno s katalogem. Zapojeno do denního agenta. Starší měsíce se doplní až přes API (požádáno 2026-11-21), ručně je nestahujeme.

## Čeká na Vítka


## Otevřené otázky

- Měny napříč marketplaces: do jaké měny převádět pro týdenní shrnutí (USD? CZK, protože výplaty z Gumroadu jdou v CZK?)
  a odkud brát kurzy (např. ČNB)? Rozhodnout před milníkem se shrnutím.

## Známé problémy

- HTTPS na Vítkově počítači jde přes certifikát, kterému věří jen úložiště Windows (antivirus/proxy). Řešeno: git → `http.sslBackend schannel`, Python → `ssl.create_default_context()`. Každý nový HTTP klient musí jet stejně.
  `uv add` potřebuje `--system-certs`.

## Rozhodnutí

- 2026-11-22 – Zkušební nákup z Gumroadu označen `exclude` (nepočítá se do součtů, v DB zůstává).

- 2026-11-22 – Historie gitu přepsána (git-filter-repo, spustil Vítek), aby v ní nebyly skutečné hodnoty z prodejů a katalogu.
  Ověřeno: žádná verze žádného souboru je neobsahuje, testy prochází i ve starých commitech. Záloha mimo repo.

- 2026-11-22 – CGTrader: z e-mailových reportů stačí jeden měsíc (říjen), zbytek až přes API.

- 2026-11-22 – Denní agent: denně 8:00, počítač nebudit, zmeškaný běh po zapnutí; upozornění na stáří stažení
  od 3 dnů. **Souhrn e-mailem každý den i bez prodejů** (místo notifikace Windows), přes Resend (zdarma, API);
  obsah: nové prodeje po kusech, součty za měsíc, stav zdrojů; později další sekce (wishlisty).
- 2026-11-21 – Cosmos agent = Playwright s vlastním profilem (pokus úspěšný); payout transakce s víc produkty se dělí
  podle skutečně zaplacených částek produktů (`items[].amount`), ne ceníku.
- 2026-11-21 – Cosmos: obě cesty (ruční kopie tabulky + agent v prohlížeči, jednou denně), společné jádro;
  Vítek souhlasí s automatizací prohlížeče (pravidlo 7). Transakce s víc produkty se dělí podle cen produktů.
  Virtual Credits se počítají jako USD.
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
