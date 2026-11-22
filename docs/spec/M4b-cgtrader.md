# Specifikace M4b: Prodeje z CGTraderu (report z e-mailu)

**Stav:** schváleno Vítkem 2026-11-22.

## Jak se report získá

1. `cgtrader.com/profile/sales`, u měsíce **View details** a pak **Generate report**.
2. Přijde e-mail s odkazem. Ten přes `links.cgtrader.com` (sledování kliknutí) přesměruje na
   `cgtrader.com/profile/reports/sales/download-latest`. Stáhne se **vždy poslední vygenerovaný report** a jen
   v prohlížeči přihlášeném na CGTrader. Stránka se neotevře, soubor se rovnou uloží do Stažených souborů,
   takže to vypadá, že odkaz nic nedělá (ověřeno 2026-11-22).
3. Soubor `sales_report.csv` Vítek přesune do `data/private/cgtrader/` a přejmenuje podle měsíce, např.
   `2026-10.csv` (každý report má stejné jméno).

## Formát (ověřeno na jednom skutečném reportu 2026-11-22)

CSV, oddělovač čárka, hlavička na prvním řádku, jeden řádek na prodej:

`OID, Purchased, Product, Product ID, Buyer, Country, Original Price, Sold For, Payment Processing, After tax,
Earning rate, Final Earnings, Transaction ID`

- `Purchased` je jen datum (`YYYY-MM-DD`), bez času a bez časové zóny.
- `Product` a `Buyer` jsou **URL** (produkt, profil kupujícího).
- Částky `Original Price` a `Sold For` mají `$`, ostatní ne (např. `0.88`, `19.11`, `11.47`). `Earning rate` je v procentech (např. `60%`).
- `Transaction ID` byl ve vzorku **prázdný** (řádek má o hodnotu méně než hlavička).

## Převod na společný model

| Společný model | CGTrader | Poznámka |
|---|---|---|
| `external_id` | `OID` | klíč `(cgtrader, OID)` |
| `product_ref` | `Product ID` | párování přes `ref` v katalogu |
| `product_title` | slug z URL `Product`, pomlčky jako mezery | report nemá název; katalog porovnává bez ohledu na velikost písmen, takže často sedí i s názvem listingu |
| `sold_at` | `Purchased` 00:00 Europe/Prague → UTC | stejně jako Fab, zóna reportu neznámá |
| `gross_cents` | `Sold For` | za kolik se skutečně prodalo, po slevě |
| `net_cents` | `Final Earnings` | podíl prodejce je proměnlivý, proto se bere hotová částka |
| `currency` | `USD` | `$` v částkách |
| `status` | `sold` | refund jsme neviděli. Záporná částka → řádek se přeskočí a vypíše |
| `raw` | řádek **bez `Buyer` a `Country`** | osobní údaje kupujícího neukládáme |

- Validace: chybí OID nebo datum, neplatná částka, `Final Earnings` > `Sold For` → řádek se přeskočí a vypíše.
  Řádek může mít o hodnotu méně než hlavička (prázdné `Transaction ID` na konci, jako ve skutečném reportu).
  Jiná hlavička → soubor se nenačte vůbec. Stejné OID v souboru dvakrát → oba řádky se přeskočí.
- Idempotence: stejný report nahraný dvakrát (i pod jiným jménem) nic nezdvojí.
- Příkaz `import cgtrader [soubor]`, bez cesty načte všechna CSV z `data/private/cgtrader/`. Denní agent ho spustí
  stejně jako Fab.
- Testy na **vymyšleném** vzorku `data/sample/cgtrader_report.csv` (vymyšlený kupující i produkt).

## Rozhodnutí Vítka (2026-11-22)

1. `Buyer` a `Country` se neukládají.

## Otevřené

- Pokrývá report vždy jeden měsíc, nebo vše? Import funguje v obou případech (stejné OID se nezdvojí).
- CGTrader posílá i **report stažení** (`Product ID, Product, Price, Downloader, Download Date, File name`).
  Nejsou to prodeje (patří sem i opakovaná stažení), import ho pozná a přeskočí. Zatím nevyužito.
