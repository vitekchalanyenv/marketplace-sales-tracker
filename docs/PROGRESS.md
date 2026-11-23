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

- 2026-11-21/22 – M4a Cosmos: **agent v prohlížeči** `sync cosmos` (Playwright, vlastní profil, headless, zachytí
  JSON z API stránky). Testy prošly, **ověřeno na skutečném účtu**: všechny transakce, tržba i payout sedí na cent,
  druhý běh 0 nových (zastaví na 1. stránce). **Ruční kopie** `import cosmos` (záložní cesta), ověřeno na skutečném
  vzorku: transakce stejné jako z API (čas na minutu, částky na cent), jen odhad dělení u transakce se dvěma produkty
  ±2 ¢ (součet přesný); data z agenta nepřepíše.
- 2026-11-22 – M4b CGTrader: `import cgtrader` (CSV report z e-mailu, bez kupujícího a země; report stažení se
  přeskočí). **Ověřeno na skutečném reportu**: částky sedí s CSV, druhý import 0 nových, spárováno.
- 2026-11-22 – M5 denní agent: `run daily` (všechny zdroje, každý krok zvlášť, log v `data/private/logs/`), úloha
  v Plánovači (`scripts/install_task.ps1`, denně 8:00, zmeškaný běh po zapnutí PC). **Ranní souhrn e-mailem přes
  Resend každý den** (nové prodeje, refundy, měsíc, stav zdrojů). **Ověřeno:** e-mail dorazil do Vítkovy schránky,
  běh přes Plánovač bez okna konzole. Notifikace Windows (první verze) nepřišla, nahrazena e-mailem.
- 2026-11-22 – M5b (spec `docs/spec/M5b-tyden-meny-demo.md`): **týdenní shrnutí** v pondělním e-mailu (čísla od kódu,
  komentář Claude jen se zástupnými značkami, deterministická kontrola + eval v `tests/test_weekly.py`), **částky v Kč** kurzem ČNB ke dni
  prodeje, `exclude` pro zkušební prodeje, `demo` na vymyšlených datech, **CI** (GitHub Actions, Windows + Linux),
  README pro čtenáře. Testy prošly (339). Po nezávislé kontrole 2026-11-22 kontrola předělána na zástupné
  značky (dřív propouštěla přehozená čísla a vymyšlený směr), demo a souhrn vyčištěny (viz AI_CHYBY). **Ověřeno:** Kč sedí s ručním přepočtem; komentář Claude ze skutečného API
  (`--dry-run --with-claude`) prošel kontrolou napoprvé, i ve verzi se značkami. **Eval na skutečném modelu**
  (`scripts/eval_commentary.py`, 20 běhů na demo týdnu): 20× napoprvé, 0× po opakování, 0× vzdáno. Slabina je obsah:
  komentář opakoval skoro všechna čísla a špatná shoda („se prodalo 4 kusy“). Prompt v2 (vybrat 1–2 věci, neopakovat
  přehled, pozor na shodu): 20× napoprvé, značek s čísly 12,8 → 0,9, riziko shody 17 → 0 z 20 (`docs/eval/`).
- 2026-11-23 – M6 přehled (spec `docs/spec/M6-prehled.md`): `dashboard` (Streamlit, jen 127.0.0.1, bez statistik),
  čísla za tento / minulý měsíc / letos, graf po měsících podle marketplace, produkty napříč platformami, posledních
  20 prodejů, stav zdrojů, filtry období a marketplace; USD/EUR i Kč. Výpočty v `overview.py`, `demo --dashboard`,
  screenshot v README. Testy prošly (361). **Ověřeno na skutečných datech:** součty tohoto měsíce po marketplacech
  (kusy, měna, Kč) shodné s ranním e-mailem, kurzy ČNB pro starší dny doplněny bez chyby, stránka se vykreslí.
  Čeká na Vítkovu kontrolu v prohlížeči.

## Rozpracováno

- M4b CGTrader přes API: čeká se na schválení přístupu (požádáno 2026-11-21). Starší měsíce se doplní až přes API.

## Čeká na Vítka

- Nic. Přečíst README (psané jeho hlasem) a potvrdit, že sedí.

## Otevřené otázky / neověřeno

- Ranní e-mail při vypršeném přihlášení do Cosmosu; doběhnutí po úplném vypnutí PC (po spánku ověřeno).
- Cosmos: formát refundu (`refund_details`) – zatím žádný nebyl; jak dlouho vydrží přihlášení.
- Další sekce souhrnu (wishlisty), M7 portfolio.

## Známé problémy

- HTTPS na Vítkově počítači jde přes certifikát, kterému věří jen úložiště Windows (antivirus/proxy). Řešeno: git → `http.sslBackend schannel`, Python → `ssl.create_default_context()`. Každý nový HTTP klient musí jet stejně.
  `uv add` potřebuje `--system-certs`.

## Rozhodnutí

- 2026-11-23 – **Ověřeno ostře:** PC v 8:00 spalo, po probuzení v 16:32 Plánovač úlohu sám doběhl v 16:38 (kód 0),
  odešel první pondělní e-mail s týdenním shrnutím a komentářem Claude (prošel kontrolou). Komentář obsahoval
  pravdivé, ale nekontrolované formulace mimo seznamy („po nulovém týdnu“, „všechno přišlo z Cosmosu“, „rozběhl“) –
  přesně hranice popsaná v README.
- 2026-11-22 – Měny: ukládá se původní měna, součty se převádí na Kč kurzem ČNB ke dni prodeje (spec M5b).
  Ověřeno na skutečných datech: částky v Kč sedí s ručním přepočtem kurzy ČNB.
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
