# Specifikace M5: Denní agent

**Stav:** schváleno Vítkem 2026-11-22.

## Cíl

Jednou denně se samo spustí stažení prodejů ze všech zdrojů. Vítek dostane **notifikaci ve Windows**:
- jsou nové prodeje (kolik a za kolik),
- něco selhalo, hlavně **vypršelo přihlášení do Cosmosu** (s návodem `sync cosmos --login`),
- agent dlouho neproběhl úspěšně.

Když je vše v pořádku a nic nového nepřibylo, notifikace se nezobrazí (jen zápis do logu).

## Spouštění: Plánovač úloh Windows

- Úloha `marketplace-sales-tracker` **denně v 8:00** (rozhodnutí Vítka 2026-11-22).
- **Počítač byl v 8:00 vypnutý:** zapne se volba „Spustit co nejdříve po zmeškaném spuštění“
  (`StartWhenAvailable`). Úloha se pak spustí po zapnutí a přihlášení.
- **Běží jen při přihlášeném Vítkovi.** Jinak by notifikace nebyla vidět a Chrome by neměl Vítkův profil.
- Počítač se **nebudí** (rozhodnutí Vítka): úloha poběží až po zapnutí.
- Spouští se přímo `.venv\Scripts\pythonw.exe -m sales_tracker run daily` s pracovní složkou projektu,
  aby v 8:00 nevyskočilo okno konzole.
- Úlohu zaregistruje skript `scripts/install_task.ps1` (a `scripts/uninstall_task.ps1`), aby to šlo zopakovat
  a nebylo potřeba klikat v Plánovači.

**Zmeškané dny se dorovnají samy:** Gumroad bere posledních 30 dní a Cosmos stránkuje, dokud nenarazí na známé
transakce starší než 30 dní. Když agent pár dní neběží, další běh doplní všechno chybějící.

## Příkaz `run daily`

Postupně spustí kroky. **Každý krok běží samostatně**: chyba jednoho nezastaví ostatní.

1. `sync gumroad`
2. `sync cosmos` (headless, bez `--login`; přihlášení nikdy nedělá agent)
3. `import fab`: soubory v `data/private/fab/` (idempotentní, už naimportované nic nezmění)
4. CGTrader a ruční kopie Cosmosu: doplní se, až budou importy (M4b, M4a cesta 2)

Výsledek každého kroku: `ok` (počet nových prodejů a jejich tržba) / `chyba` (krátký důvod, typ chyby).

## Notifikace

| Situace | Text (návrh) |
|---|---|
| nové prodeje | „3 nové prodeje, čistě 42,50 USD (Cosmos 2, Gumroad 1)“ (čistý příjem po poplatcích) |
| nové refundy | „1 refund“ |
| vypršelo přihlášení Cosmos | „Cosmos: přihlas se – `uv run python -m sales_tracker sync cosmos --login`“ |
| jiná chyba | „Gumroad: chyba (síť / token). Detail v logu.“ |
| zdroj selhal a poslední úspěch je 3 a víc dní starý | k chybě se připíše „naposledy staženo před 4 dny“ |

- Bez tokenů, bez osobních údajů zákazníků. Jen počty, částky a název zdroje.
- Součet tržby jen v rámci jedné měny (převod měn je otevřená otázka týdenního shrnutí).
- Notifikace přes knihovnu `windows-toasts`. Před zapojením ji ověří jeden testovací toast.
  Když notifikace selže, agent kvůli tomu nespadne a výsledek najdeš v logu.

## Log a stav

- `data/private/logs/daily_YYYY-MM-DD.log`: výstup všech kroků (mimo git). Logy starší než 60 dní se mažou.
- `data/private/agent_state.json`: čas posledního úspěšného běhu každého zdroje (pro hlášku „nestáhl se N dní“).
- Nové prodeje a refundy se zjistí porovnáním databáze před a po krocích, takže se stávající kroky nemusí
  měnit. Nové prodeje jsou záznamy přidané během běhu se statusem `sold` (podle `rowid`; `first_seen_at` má
  přesnost jen na sekundy). Refundy jsou záznamy, které mají po běhu jiný status než `sold` a před během ho neměly.
- Hlídání stáří platí pro automatické zdroje (Gumroad, Cosmos). Fab se nahrává ručně, tam se nehlídá.

## Testy (bez sítě, prohlížeče a skutečných notifikací)

- Kroky podvržené funkcemi: vše ok bez nových → žádná notifikace; nové prodeje → jedna notifikace se součtem;
  `SessionExpired` → notifikace s `--login`; jeden krok spadne, ostatní doběhnou.
- Stav: zdroj bez úspěchu > 3 dny → upozornění; úspěch stav obnoví.
- Návratový kód `run daily`: 0 když vše ok, 1 když něco selhalo.
- Registrace úlohy v Plánovači se ověřuje ručně (`Get-ScheduledTask`, ruční spuštění úlohy).

## Rozhodnutí Vítka (2026-11-22)

1. Notifikace i při nových prodejích, ne jen při chybě.
2. Počítač nebudit, spustit až po zapnutí.
3. Upozornění na stáří stažení od 3 dnů.

## Mimo rozsah M5

Týdenní shrnutí (samostatný milník), e-mailové notifikace, běh na serveru nebo v cloudu (Cosmos potřebuje
Vítkův profil v Chromu na tomhle počítači).
