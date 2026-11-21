# Specifikace M4a: Prodeje z Cosmosu (Leartes)

**Stav:** návrh 2026-11-21, čeká na schválení Vítkem a odpovědi na otázky na konci.
CGTrader bude mít vlastní spec (M4b), až bude známý formát reportu z e-mailu, případně API.

## Cíl

Prodeje z Cosmosu se dostanou do `data/private/sales.db` **dvěma vyměnitelnými cestami** se společným jádrem:

1. **Ruční kopie:** Vítek zkopíruje tabulku Reports → Sales do textového souboru a spustí `import cosmos`.
2. **Agent v prohlížeči:** `sync cosmos` jednou denně sám projde tabulku ve Vítkově přihlášeném prohlížeči.

Obě cesty vytvoří stejné „surové řádky“ a dál běží **stejný kód** (převod, rozdělení, uložení, párování).
Je to zároveň ukázka modulárního návrhu do portfolia: zdroj dat jde vyměnit, logika zůstává.

```
ruční kopie (.txt) ──► parser textu ──┐
                                      ├─► CosmosRow ─► převod na Sale (rozdělení podle cen) ─► DB ─► párování
prohlížeč (Playwright) ─► čtení DOM ──┘
```

## Co víme o Cosmosu (`docs/ZDROJE.md`, průzkum 2026-11-21)

- Portál `publisher.leartesstudios.com/sales`, tabulka: `Transaction ID`, `Products`, `Amount`, `Payout`, `Date`.
- Bez exportu a bez JSON API (data přicházejí rovnou v HTML).
- Transakce může mít **víc produktů**; částky jsou jen za celou transakci.
- U produktu je název a **slug** → párování přes slug.
- Částky `"<číslo> USD"`, výjimka **Virtual Credits** (částka bez měny, payout jen text).
- `Date` = `YYYY-MM-DD HH:MM` v čase Europe/Prague.

## Společné jádro

**`CosmosRow`** (výstup obou cest): `transaction_id` (text bez `#`), `products` (seznam `(název, slug)`),
`amount` (text), `payout` (text), `date` (text). Kontroly formátu jsou na jednom místě.

**Převod na záznamy v `sales`:** jeden záznam **na každý produkt v transakci**.

| Společný model | Cosmos | Poznámka |
|---|---|---|
| `external_id` | `<transaction_id>\|<slug>` | např. `20001\|sample-medieval-village` |
| `product_ref` | slug | párování přes `ref` v katalogu |
| `product_title` | název produktu | |
| `sold_at` | `Date` v Europe/Prague → UTC | |
| `quantity` | 1 | |
| `gross_cents` | `Amount` (rozdělené, viz níže) | |
| `net_cents` | `Payout` (rozdělené stejně) | u Virtual Credits viz otázka 3 |
| `currency` | `USD` | kredity se berou jako USD (rozhodnutí Vítka) |
| `status` | `sold` | refundy viz otázka 4 |
| `raw` | celý `CosmosRow` + zdroj (`paste` / `browser`) + index produktu | |

**Rozdělení transakce s víc produkty (rozhodnutí Vítka: podle cen):**
- Katalog dostane u listingu na Cosmosu cenu: `- ref: sample-…` + `price: 19.90` (USD).
- Podíl produktu = jeho cena / součet cen produktů v transakci. Centy se rozdělí metodou největšího zbytku,
  takže **součet částí je vždy přesně celá částka** (žádný ztracený cent).
- Když některý produkt transakce nemá v katalogu cenu → transakce se **přeskočí a vypíše** („doplň cenu“).
  Nic se nerozdělí odhadem.
- Transakce s jedním produktem cenu nepotřebuje.

**Idempotence:** klíč `(cosmos, transaction_id|slug)`. Ruční kopie i agent můžou stejné prodeje načíst opakovaně.

## Cesta 1: ruční kopie – `import cosmos [soubor]`

- Vítek na Sales nastaví největší velikost stránky, označí tabulku, zkopíruje a vloží do
  `data/private/cosmos/<datum>.txt`. Víc stránek = víc vložení do stejného souboru (řádky hlavičky se přeskočí).
- Bez cesty se naimportují všechny `*.txt` z `data/private/cosmos/` (jako u Fabu).
- **Přesný tvar zkopírovaného textu zatím neznáme.** Před implementací parseru potřebuju jeden skutečný vzorek
  (viz otázka 1). Parser se napíše podle něj, ne podle odhadu.

## Cesta 2: agent v prohlížeči – `sync cosmos`

- **Playwright** (Chromium) s **vlastním trvalým profilem** v `data/private/browser/cosmos/` (mimo git).
  Vítek se v něm **jednou přihlásí sám** (`sync cosmos --login` otevře okno a počká). Heslo nikdy neprochází kódem,
  `.env` ani logem. Uložená session cookies jsou jen v tom profilu.
- Běh: otevře `/sales`, přečte řádky tabulky z DOM a po stránkách jde dál, **dokud nenarazí na stránku, kde už jsou
  všechny transakce v DB** (běžně stačí 1. stránka). Mezi stránkami pauza 3–5 s, max. 1 běh denně
  (časování a plánovač Windows až v M5). Prohlížeč jen čte: žádné klikání mimo stránkování.
- Když session vyprší (přesměrování na přihlášení) → hláška „přihlas se: sync cosmos --login“, nic se neuloží.
- Když se změní struktura stránky (nenajde tabulku nebo sloupce) → hláška a **screenshot do `data/private/`**,
  nic se neuloží.
- Selektory jsou na jednom místě, aby oprava po změně webu byla jedna úprava.

## Chyby a výpis

Stejně jako Fab: na konci `Cosmos (<zdroj>): transakcí N, záznamů M, nových, aktualizovaných, přeskočeno`, pak párování.
Přeskočené transakce: ID + důvod (bez dalších údajů).

## Testy (bez sítě a bez prohlížeče, vymyšlená data)

- Převod `CosmosRow` → záznamy: jeden produkt, víc produktů (rozdělení podle cen, součet sedí na cent, i při
  nedělitelných částkách), chybějící cena → přeskočení, Virtual Credits, čas v zóně, idempotence.
- Parser ručně zkopírovaného textu na vymyšleném vzorku ve stejném tvaru jako skutečný (až bude).
- Čtení DOM: na **uloženém vymyšleném HTML** (`data/sample/cosmos_sales.html`) přes Playwright offline
  (`page.set_content`), bez sítě. Ostrý běh proti webu se testuje ručně.
- Testy nesahají na `data/private/` ani na síť.

## Nové závislosti

`playwright` (+ jednorázově `uv run playwright install chromium`, cca 150 MB). Jen pro cestu 2.

## K rozhodnutí (Vítek)

1. **Vzorek ruční kopie:** zkopíruješ jednou tabulku Sales (Ctrl+A / označení tabulky, Ctrl+C) do
   `data/private/cosmos/vzorek.txt`? Podle něj napíšu parser.
2. **Ceny na Cosmosu** pro rozdělení: pošleš ceny svých 3 produktů na Cosmosu, nebo si je mám přečíst ze stránky
   Products v Cosmosu (jen čtení)?
3. **Virtual Credits – čistý příjem:** částku v kreditech beru jako USD (`gross`). Payout v USD ale chybí.
   Návrh: `net` nechat prázdný (neznámý). Nebo víš, kolik za kreditní prodej skutečně dostaneš?
4. **Refundy:** v Cosmosu je sekce Refund Requests. Mám se na ni podívat (jen čtení) a refundy zahrnout do M4a,
   nebo je zatím vynechat?
5. **Playwright:** souhlasíš s novou závislostí a stažením Chromia (~150 MB)?

## Mimo rozsah M4a

CGTrader (M4b), plánovač a denní běh (M5), automatické přihlašování (nikdy – přihlašuje se Vítek sám).
