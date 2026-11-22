# Specifikace M5b: týdenní shrnutí od Claude, měny, zkušební prodeje, demo

**Stav:** schváleno Vítkem 2026-11-22. Body podle Vítkova seznamu „Co dotáhnout“
(README a GitHub Actions nepotřebují spec; CI už běží).

## 1. Měny (otevřená otázka z PROGRESS)

- Prodeje se dál ukládají **v původní měně** (beze změny).
- Pro součty se převádí do **CZK kurzem ČNB** platným **v den prodeje** (místní datum).
- Zdroj ověřen 2026-11-22 jedním requestem:
  `https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/denni_kurz.txt?date=DD.MM.YYYY`
  vrací text: 1. řádek `20.11.2026 #223`, 2. řádek hlavička `země|měna|množství|kód|kurz`, pak řádky typu
  `USA|dolar|1|USD|22,262` (desetinná čárka; `množství` může být 100).
- Kurzy se ukládají do tabulky `fx_rates(day, currency, czk_per_unit)` jako `Decimal` text, každý den se stahuje
  nejvýš jednou. Víkend a svátek: ČNB vrací poslední platný kurz. Že to tak opravdu dělá, se ověří jedním
  requestem na sobotní datum, než se na to kód spolehne.
- Převedená částka = `Decimal` → haléře, zaokrouhlení ROUND_HALF_UP. V souhrnu se zobrazí obojí, např.
  `čistě 45,90 USD (≈ 1 021,74 Kč)`.
- Když kurz nejde stáhnout, souhrn se pošle bez Kč a se stavem „kurz ČNB nedostupný“.

## 2. Zkušební prodeje

- Nový sloupec `excluded` (0/1) a `excluded_reason` v `sales`. Upsert ho **nepřepisuje**, takže označení
  vydrží každý další sync.
- Příkaz `exclude <marketplace> <external_id> --reason "zkušební nákup"` (a `--undo`).
- Označené prodeje se **nepočítají** do součtů v denním e-mailu, týdenním shrnutí ani v demu. V databázi
  zůstávají a `catalog check` je dál ukazuje.
- Po schválení se tak označí Vítkův zkušební nákup z Gumroadu.

## 3. Týdenní shrnutí od Claude s pojistkou

Cíl: ukázat, jak AI zapojit tak, aby **nevymýšlela čísla**.

- **Kdy:** v pondělí. Ranní e-mail dostane navíc sekci **„Minulý týden“** nahoře a v předmětu `· týdenní
  shrnutí`. Zůstává jeden e-mail denně.
- **Čísla počítá kód** z DB (bez vyloučených prodejů) za minulý týden po–ne v místním čase:
  - prodeje a čistý příjem po marketplacech a produktech (v původní měně a v Kč),
  - srovnání s předchozím týdnem,
  - nejprodávanější produkt,
  - součet za měsíc.
  Kódem spočítaná čísla jsou v e-mailu vždycky, i bez Claude.
- **Claude píše jen komentář** (2–4 věty česky), například „tento týden se nejvíc prodávala…“. Dostane jen
  hotová čísla jako JSON a pokyn, že smí použít výhradně čísla z dat.
  - Model `claude-opus-5-5` (výchozí podle dokumentace Anthropicu), `effort: low`, protože jde o krátký text.
  - Oficiální SDK `anthropic`, klíč `ANTHROPIC_API_KEY` v `.env`.
  - Odhad ceny: stovky až nižší tisíce tokenů jednou týdně, tedy **řádově centy za měsíc**.
  - Zapnutý serverový `fallbacks: "default"` (záložní model, když bezpečnostní filtr požadavek odmítne).
- **Pojistka (kontrola po odpovědi, deterministická, bez AI):**
  - Z komentáře se vytáhnou všechna čísla (částky, počty, procenta, data).
  - Každé musí odpovídat hodnotě v datech pro Claude. Toleruje se zápis (`45,90` = `45.90`), procento se smí
    lišit nejvýš o 1 kvůli zaokrouhlení. Slovní číslovky „jeden“ až „deset“ se kontrolují taky.
  - Když kontrola neprojde, jednou se zkusí znovu. Když neprojde ani podruhé, e-mail odejde **jen s čísly
    od kódu** a s poznámkou „komentář neprošel kontrolou“ (rozhodnutí Vítka). Zamítnutý text se zapíše do logu.
  - Chybí klíč, API je nedostupné nebo odmítne → e-mail odejde bez komentáře a s důvodem.
- **Eval:** testy s podvrženým Claude (bez sítě):
  - komentář jen se správnými čísly projde,
  - vymyšlené číslo, přehozená částka, špatný počet nebo procento mimo toleranci neprojdou,
  - opakovaný pokus funguje,
  - výpadek API nevadí.

  Plus sada 10–15 ručně napsaných komentářů (dobrých i špatných) v `tests/`, na kterých se měří kontrola.
  Ostrý běh proti API jednou ručně, s Vítkovým souhlasem (stojí peníze).
- `run daily --dry-run` týdenní sekci jen vypíše a Claude nevolá. Volat ho bude `--dry-run --with-claude`.

## 4. Demo režim

- `python -m sales_tracker demo`: celý pipeline na **vymyšlených** datech z `data/sample/`, bez účtů, sítě
  a `.env`. Recruiter si to vyzkouší za minutu.
  - Dočasná DB v tempu, nic nesahá na `data/private/`.
  - Gumroad z ukázkových JSON přes podvržený HTTP, Cosmos z ukázkových stránek API i z ruční kopie, Fab
    a CGTrader z ukázkových CSV.
  - Pak párování s ukázkovým katalogem, ranní souhrn (vypíše se, neodešle) a týdenní čísla. Kurz je pevný
    ukázkový a v demu se ČNB nevolá. Komentář Claude se v demu nahradí poznámkou „(v ostrém běhu sem Claude
    napíše komentář, ověřený kontrolou čísel)“.
  - Datum „dnes“ je v demu pevné (podle dat ve vzorcích), takže výstup je pokaždé stejný.
- Test: `demo` doběhne s kódem 0, výpis obsahuje všechny marketplaces a nesáhne na `data/private/`.

## Pořadí prací

1. Zkušební prodeje (malé, hned se projeví v součtech).
2. Měny (ČNB + tabulka kurzů).
3. Demo.
4. Týdenní shrnutí s pojistkou.
5. README pro čtenáře (screenshot ranního e-mailu z dema, diagram, „What the AI got wrong“).

## Rozhodnutí Vítka (2026-11-22)

1. Cílová měna CZK, kurz ČNB ke dni prodeje.
2. Komentář neprojde kontrolou ani napodruhé → e-mail jen s čísly od kódu, bez komentáře.
3. Týdenní shrnutí jako sekce pondělního ranního e-mailu.
4. API klíč Anthropicu založí Vítek (console.anthropic.com, kredit, klíč do `.env`). Do té doby se vše testuje
   s podvrženým Claude, ostrý běh až s klíčem.
