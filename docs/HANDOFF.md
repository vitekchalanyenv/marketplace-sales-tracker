# Předání

**Relace:** 2026-11-21 až 22 (M4 dokončení, M5 denní agent, M5b týdenní shrnutí/měny/demo, úklid dat, README)

## Kde jsme

- **M1–M5 hotové** (podrobně `docs/PROGRESS.md`). Zdroje:
  - Gumroad: API.
  - Cosmos: agent v prohlížeči, záložně ruční kopie.
  - Fab: CSV.
  - CGTrader: CSV z e-mailu; API čeká na schválení.
- **Denní agent:** Plánovač úloh `marketplace-sales-tracker`, denně 8:00, běží `pythonw -m sales_tracker run daily`.
  Ranní e-mail přes Resend chodí každý den: nové prodeje, refundy, měsíc v USD i Kč (ČNB), stav zdrojů.
  - V pondělí navíc sekce **„Minulý týden“**. Čísla počítá kód, komentář píše Claude (`claude-opus-5-5`, effort low,
    `fallbacks: "default"`).
  - Kontrola (`weekly.check`) pustí jen čísla, která jsou v datech. Když neprojde ani napodruhé, jdou jen čísla
    (rozhodnutí Vítka).
- `.env`: `GUMROAD_ACCESS_TOKEN`, `RESEND_API_KEY`, `REPORT_EMAIL_TO`, `ANTHROPIC_API_KEY` (všechny vyplněné).
- `exclude`: Vítkův zkušební nákup z Gumroadu je vyloučený ze součtů.
- **Demo:** `uv run python -m sales_tracker demo` na vymyšlených datech. Screenshot do README dělá
  `scripts/demo_screenshot.py`.
- **CI:** GitHub Actions (pytest + ruff, Windows i Linux), zelené.
- **Historie gitu přepsaná** bez skutečných hodnot (git-filter-repo, spustil Vítek). Ověřeno strojovým prohledáním
  všech verzí souborů.
- Testy **311 passed**, ruff čistý (2026-11-22).

## Co udělat dál

1. **Zkontrolovat první pondělní e-mail** (23. 11.) a týdenní komentář. Při potížích je detail
   v `data/private/logs/daily_2026-11-23.log`, kam se zapisuje i zamítnutý komentář.
2. **CGTrader API**, až ho schválí: spec a stahování. Nahradí ruční reporty a doplní starší měsíce.
3. **M6 přehled** (dashboard: celkem / marketplace / produkt / v čase). Nejdřív spec.
4. **Další sekce ranního e-mailu** (wishlisty apod.). Souhrn je seznam `Section`, takže se snadno rozšiřuje.
5. **M7 portfolio:** README je hotové. Zbývá video a případně krátký write-up o kontrole čísel.

## Otevřené otázky / neověřeno

- E-mail při vypršeném přihlášení do Cosmosu a doběhnutí zmeškaného běhu po zapnutí PC zatím nikdo neviděl ostře.
- Cosmos: formát refundu neznámý a nevíme, jak dlouho vydrží přihlášení.
- README je psané Vítkovým hlasem. Vítek ho má přečíst a potvrdit.

## Pozor

- HTTPS jen přes úložiště certifikátů Windows: Python `ssl.create_default_context()`, git `schannel`,
  `uv add --system-certs`.
- **Do repa nikdy skutečné hodnoty**, ani „upravené“: částky, ID, slugy, názvy produktů, časy ani počty prodejů.
  Ukázky jen vymyšlené (`data/sample/`). Před commitem dělat grep diffu. Klasifikátor commit s únikem zastaví.
- Testy nikdy nesahají na `data/private/`, síť, prohlížeč ani skutečné API (Claude, Resend, ČNB jsou podvržené).
- Ostré volání Claude stojí peníze. Spouštět jen s vědomím Vítka (`run daily --dry-run --with-claude`).
- Kurz ČNB na dnešek se neukládá do mezipaměti, protože vychází až odpoledne.
- Mazání souborů mimo repo (např. ve Stažených) je v tomto prostředí blokované, takže to nechat na Vítkovi.
- Přepis historie a force-push dělá Vítek sám, agent je zablokovaný.
- V heredocu s Pythonem pozor na `\n`; víceřádkové úpravy dělat raději nástrojem Edit.

## Úklid u Vítka

- Smazat zálohu repa před přepisem (scratchpad `backup-before-rewrite.git`) a `data/private/history-replacements.txt`.
  V obou jsou ještě skutečné hodnoty.
- Smazat dvě kopie `sales_report.csv` ve Stažených.

## Jak pracovat

- `/navazani` na začátku, `/predani` na konci.
