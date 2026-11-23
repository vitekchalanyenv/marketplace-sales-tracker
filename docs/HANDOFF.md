# Předání

**Relace:** 2026-11-23 (ověřený pondělní e-mail, M6 přehled, doplněná historie Fab/CGTrader, M7 write-up,
průzkum wishlistů, M5c ruční zdroje a měsíční shrnutí)

## Kde jsme

- **M1–M6 hotové, M5c hotové** (podrobně `docs/PROGRESS.md`). Zdroje:
  - Gumroad: API.
  - Cosmos: agent v prohlížeči, záložně ruční kopie. Data za celý rok.
  - Fab: CSV report (od začátku roku) v `data/private/fab/`, nahrává Vítek ručně.
  - CGTrader: měsíční CSV reporty z e-mailu v `data/private/cgtrader/`; report „Item downloads“ se přeskočí.
    API čeká na schválení.
- **Denní agent:** Plánovač úloh `marketplace-sales-tracker`, denně 8:00, zmeškaný běh doběhne po probuzení
  (ověřeno ostře 23. 11.). Ranní e-mail přes Resend každý den:
  - nové prodeje, refundy, měsíc v USD/EUR i Kč (ČNB), stav zdrojů;
  - **nově (M5c):** u Fabu „ok – data do …“, varování po 7 dnech i v předmětu; u CGTraderu „ok – reporty do …“,
    varování po 10. dni bez reportu za minulý měsíc (jen v sekci; měsíc bez prodeje taky varuje);
  - **nově (M5c):** první e-mail měsíce má sekci „Minulý měsíc“ (jen čísla, žádný Claude), stav
    `monthly_sent_for` v `agent_state.json`;
  - v pondělí „Minulý týden“ s komentářem Claude přes zástupné značky a kontrolu (beze změn).
- **Přehled (M6):** `uv run python -m sales_tracker dashboard` (Streamlit, jen 127.0.0.1, headless, prohlížeč
  otevře sám). Data se drží 10 min, tlačítko „Načíst znovu“. Demo: `... demo --dashboard`. Výpočty `overview.py`
  sdílí i měsíční sekce e-mailu.
- **Portfolio:** README (s přehledem a screenshotem), `docs/writeup.md` o kontrole čísel v komentáři Claude.
- Testy **376 passed**, ruff čistý (2026-11-23).

## Co udělat dál

1. **Zkontrolovat zítřejší e-mail (24. 11.)**: řádky Fab/CGTrader ve stavu zdrojů.
2. **1. 12. zkontrolovat měsíční sekci** za listopad. Do 10. 12. stáhnout CGTrader report za listopad, jinak přijde
   varování (11. 12.). Fab report obnovovat aspoň jednou týdně.
3. **CGTrader API**, až ho schválí: spec a stahování. Nahradí ruční reporty i odhad „chybí report“.
4. Možné dál (nic zadáno): záloha databáze, další sekce e-mailu. Wishlisty a video jsou odložené (Vítek).

## Otevřené otázky / neověřeno

- E-mail při vypršeném přihlášení do Cosmosu a doběhnutí po úplném vypnutí PC (po spánku ověřeno).
- Cosmos: formát refundu neznámý, nevíme, jak dlouho vydrží přihlášení.
- README a write-up: Vítek je má přečíst a potvrdit.

## Pozor

- HTTPS jen přes úložiště certifikátů Windows: Python `ssl.create_default_context()`, git `schannel`,
  `uv add --system-certs`.
- **Do repa nikdy skutečné hodnoty**, ani v „příkladech“ ve spec: částky, ID, slugy, názvy produktů, časy ani počty.
  Ukázky vymýšlet od nuly. Před commitem grep diffu. Klasifikátor commit s únikem zastaví.
- Testy nikdy nesahají na `data/private/`, síť, prohlížeč ani skutečné API.
- Ostré volání Claude stojí peníze, jen s vědomím Vítka (`run daily --dry-run --with-claude`).
- Streamlit vždy `--server.headless true` (jinak první běh čeká na e-mail na stdin).
- Kurz ČNB na dnešek se neukládá do mezipaměti.
- Mazání souborů mimo repo a přepis historie dělá Vítek.
- V Git Bash není `python`, spouštět přes `uv run python`.

## Úklid u Vítka

- Smazat zálohu repa před přepisem (scratchpad `backup-before-rewrite.git`) a `data/private/history-replacements.txt`.
- Ve Stažených smazat kopie reportů: `sales_report*.csv`, `cg_trader_12monthsback.csv`, `item_downloads_report.csv`
  a Fab CSV (originály jsou v `data/private/`).

## Jak pracovat

- `/navazani` na začátku, `/predani` na konci.
