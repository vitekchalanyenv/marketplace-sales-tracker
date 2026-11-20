# Specifikace M3: Import denního reportu z Fabu

**Stav:** návrh 2026-11-20, čeká na schválení Vítkem a odpovědi na otázky na konci.

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
| `sold_at` | `Day` 00:00 UTC | viz otázka 4 |
| 🆕 `quantity` | `Net Units` | nové pole, viz otázka 3; může být záporné |
| `gross_cents` | `Net Sales` v centech | může být **záporné** (refund) |
| `net_cents` | viz otázka 2 | |
| `currency` | `USD` | viz otázka 5 |
| `status` | `sold`, záporný řádek → `refunded` | viz otázka 1 |
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

- Převod řádku: centy (`7.5` → 750, `12.0` → 1200), `quantity`, záporný řádek = refund, UTC datum, měna.
- Klíč: stejný den, listing a licence, jiná cena → dva záznamy.
- Opakovaný import stejného souboru → 0 nových. Překrývající se report → jen nové dny přibudou. Změna `Net Units` → aktualizace.
- Validace: všechny situace z tabulky. Špatná hlavička → nic se neuloží.
- Soubor s BOM a s LF i CRLF se načte stejně (Excel při uložení BOM přidává).
- Párování na vzorový katalog.

## K rozhodnutí (Vítek)

1. **Refundy na Fabu** jsou samostatné záporné řádky a nedají se přiřadit k původnímu prodeji. Návrh: uložit je jako
   samostatný záznam se záporným `gross_cents` a `status = refunded`. Součty pak vychází správně samy.
   U Gumroadu refund mění stav původního prodeje, u Fabu je to vlastní řádek („každý marketplace to čte po svém“).
2. **Čistý příjem:** report poplatek Fabu neobsahuje. Z mé paměti má Fab podíl tvůrce 88 % (poplatek 12 %), ale **ze zdroje ani z tvých dat
   to ověřené není**. Návrh A: `net_cents` nechat prázdné, dokud nebude zdroj (např. výplatní report).
   Návrh B: počítat 88 % s poznámkou „odhad“. Co chceš? Máš ve Fabu i výplatní / payout report?
3. **Počet kusů:** přidat do společného modelu `quantity`? Fab má v řádku i 2 kusy, u Gumroadu je `quantity` také
   (u stávajících prodejů by se doplnilo 1). Návrh: ano.
4. **Časová zóna `Day`:** report ji neuvádí. Návrh: brát jako UTC (Epic/Fab reporty obvykle bývají v UTC – **neověřeno**).
   Pro denní přehledy je rozdíl max. jeden den.
5. **Měna:** v reportu není. Návrh: USD (ceny na Fabu jsou v dolarech). Potvrdíš, že ve Fabu vidíš ceny a výplaty v USD?
6. **Jak budeš reporty stahovat?** Návrh: kdykoli stáhneš libovolné období, uložíš do `data/private/fab/` a spustíš
   import; překryvy nevadí. Případně `import fab` bez cesty naimportuje všechny soubory z `data/private/fab/`.

## Mimo rozsah M3

Automatické stahování z Fabu (žádné API, ruční stažení stačí), Cosmos a CGTrader (M4), přehledy (M6).
