# Specifikace M3: Import denního reportu z Fabu

**Stav:** schváleno Vítkem 2026-11-21, otázky 1–6 rozhodnuty (viz konec).
**Implementace:** napsáno, testy prošly (157 celkem), **ověřeno na skutečném reportu** 2026-11-21: součet `Net Sales`
a `Net Units` v DB sedí s CSV, opakovaný import 0 nových, všechny řádky spárované s katalogem.

## Cíl

`uv run python -m sales_tracker import fab <soubor.csv>` načte CSV report stažený ručně z Fabu a uloží řádky do
`data/private/sales.db`. Opakovaný import (i překrývajících se období) nevytvoří duplicity. Vadné řádky se nahlásí.

## Co víme o reportu (ze skutečného souboru, 2026-11-20)

Skutečný report leží v `data/private/fab/` (mimo git). Tady je **jen formát**, příklady hodnot jsou vymyšlené.
Podrobně v `docs/ZDROJE.md`.

- Název souboru od Fabu: `<od>_<do>_fab_daily_sales_report.csv` (např. `2026-10-01_2026-11-20_…`).
- UTF-8 bez BOM, oddělovač čárka, konce řádků CRLF, hlavička na 1. řádku. Přesně 9 sloupců:
  `Day, Source, Listing Title, License, Base Price, Total VAT, Total Tax, Net Units, Net Sales`.
- Report je **agregovaný po dnech**, ne po transakcích. Řádek = den + listing + licence (+ cena).
- `Day` je jen datum (`YYYY-MM-DD`), bez času a časové zóny.
- Částky s desetinnou tečkou, **bez pevného počtu desetin** (`7.5`, `12.0`, `19.99`), max. 2 desetinná místa,
  bez symbolu měny.
- `Net Sales` = `Base Price × Net Units` (platilo pro všechny řádky skutečného reportu).
- `Net Units` může být víc než 1 (víc prodejů téhož listingu za den).
- **Refund = samostatný záporný řádek** v den refundu (`Net Units = -1`, `Net Sales = -<cena>`). Původní prodej může
  být mimo období reportu, takže se k němu refund nedá přiřadit.
- Stejný listing a licence mají v různé dny různé `Base Price` (slevy).
- `Source` byl vždy `Fab`, `License` je `Personal` / `Professional`.
- `Total VAT` a `Total Tax` jsou daně navíc (nejsou v `Net Sales`).
- **Poplatek Fabu v reportu není.** `Net Sales` je tržba před poplatkem.
- Názvy listingů se přesně shodují s Vítkovým katalogem (všechny se spárovaly).

## Jak se řádek uloží (návrh)

Řádek reportu = jeden záznam v `sales` (marketplace `fab`).

| Společný model | Fab | Poznámka |
|---|---|---|
| `external_id` | `Day` + `Source` + `Listing Title` + `License` + `Base Price` v centech | např. `2026-01-17\|Fab\|Sample Hangar\|Personal\|1200` |
| `product_title` | `Listing Title` | párování s katalogem podle názvu |
| `product_ref` | – | Fab žádné ID nemá |
| `sold_at` | `Day` 00:00 Europe/Prague → UTC | rozhodnutí 4 |
| `quantity` | `Net Units` | nové pole; může být záporné |
| `gross_cents` | `Net Sales` v centech | může být **záporné** (refund) |
| `net_cents` | `round(Net Sales × 0,88)` | rozhodnutí 2 |
| `currency` | `USD` | |
| `status` | `Net Units < 0` → `refunded`, jinak `sold` | |
| `raw` | celý řádek (slovník sloupec → text) + název souboru | |

**Proč je v klíči i cena:** stejný den, listing a licence se může prodávat za dvě ceny (začátek nebo konec slevy).
Bez ceny by se dva řádky slily do jednoho. Ve skutečném reportu ten případ zatím nebyl, ale nedá se vyloučit.

**Opakovaný import:** stejný klíč → existující záznam. Když se změní `Net Units` / `Net Sales` (Fab den později
přepočítá), záznam se aktualizuje (`aktualizovaných 1`), stejně jako refund u Gumroadu.

## Validace

| Situace | Chování |
|---|---|
| soubor neexistuje / není UTF-8 | hláška, nic se neuloží |
| hlavička není přesně 9 očekávaných sloupců | hláška se seznamem chybějících / navíc sloupců, **nic se neuloží** (formát se změnil, je potřeba to zkontrolovat) |
| `Day` není `YYYY-MM-DD` | řádek se přeskočí a vypíše (číslo řádku + důvod) |
| částka není číslo nebo má víc než 2 desetinná místa | přeskočí se a vypíše |
| `Net Units` není celé číslo | přeskočí se a vypíše |
| `Net Sales ≠ Base Price × Net Units` | uloží se, ale vypíše se **upozornění** (zatím neznámý případ, může to být sleva nebo kupon) |
| prázdné `Listing Title` / `License` | přeskočí se a vypíše |
| dva řádky se stejným klíčem v jednom souboru | oba se přeskočí a vypíšou (nevíme, který platí) |

Peníze se čtou přes `Decimal` z textu, nikdy přes `float` (zlaté pravidlo 5).

Na konci výpis jako u Gumroadu: `Fab (soubor …): řádků 6, nových 6, aktualizovaných 0, přeskočeno 0` a potom párování
s katalogem (`spárováno / nespárováno`, jako po `sync`).

## Testy (bez sítě, vymyšlená data `data/sample/fab_report.csv`)

- Převod řádku: centy (`7.5` → 750, `12.0` → 1200), `quantity`, záporný řádek = refund, den v Europe/Prague → UTC
  (zima i léto), měna, `net = 88 %` se zaokrouhlením.
- `import fab` bez cesty načte všechny CSV ze složky.
- Klíč: stejný den, listing a licence, jiná cena → dva záznamy.
- Opakovaný import stejného souboru → 0 nových. Překrývající se report → jen nové dny přibudou. Změna `Net Units` → aktualizace.
- Validace: všechny situace z tabulky. Špatná hlavička → nic se neuloží.
- Soubor s BOM a s LF i CRLF se načte stejně (Excel při uložení BOM přidává).
- Párování na vzorový katalog.

## Rozhodnutí Vítka (2026-11-21)

1. **Refund** = samostatný záznam se záporným `gross_cents` / `net_cents` / `quantity` a `status = refunded`.
2. **Čistý příjem** = 88 % z `Net Sales` (Vítek potvrdil podíl tvůrce 88 %). `net_cents = round(Net Sales × 0,88)`
   v centech, zaokrouhlení half-up přes `Decimal`. Sazba je konstanta v kódu (`FAB_CREATOR_SHARE`).
3. **`quantity`** přibývá do společného modelu. Řádek s `Net Units = 2` je totéž, jako by tam byl dvakrát po jednom
   kusu; součty se počítají z `gross_cents` / `net_cents` řádku. Gumroad: `quantity` z odpovědi (chybí → 1),
   u existujících prodejů se doplní 1.
4. **`Day` je v místním čase Vítka (Europe/Prague).** `sold_at` = `Day` 00:00 Europe/Prague převedené na UTC
   (např. `2026-01-03` → `2026-01-02T23:00:00Z`). Při zobrazení se převede zpět na místní den.
   Windows nemá databázi časových zón → nová závislost `tzdata`.
5. **Měna** USD.
6. **Stahování:** Vítek ukládá reporty za libovolné období do `data/private/fab/`. `import fab` bez cesty
   naimportuje všechny `*.csv` z této složky (v abecedním pořadí), `import fab <soubor>` jen jeden.

## Mimo rozsah M3

Automatické stahování z Fabu (žádné API, ruční stažení stačí), Cosmos a CGTrader (M4), přehledy (M6).
