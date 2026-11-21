# Specifikace M4a: Prodeje z Cosmosu (Leartes)

**Stav:** návrh 2026-11-21; otázky 1–4 rozhodnuty, cesta 2 (automat) čeká na rozhodnutí podle
`docs/spec/M4-prohlizec-moznosti.md`. Cesta 1 (ruční kopie) a společné jádro jsou připravené k implementaci, jakmile bude vzorek.
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
- Bez exportu. Stránka čte neveřejné JSON API s tokenem v prohlížeči (viz podklad k možnostem).
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

Způsob se rozhodne podle `docs/spec/M4-prohlizec-moznosti.md` (doporučení: Playwright s vlastním profilem, který
zachytí JSON z API stránky; nejdřív krátký pokus). Pevně platí:
- přihlašuje se vždy Vítek sám (reCAPTCHA), heslo ani token neprochází kódem, `.env` ani logem,
- nejvýš 1 běh denně, pauzy mezi stránkami, jen čtení,
- výstupem jsou stejné `CosmosRow` jako u ruční kopie, dál běží společné jádro,
- když session vyprší nebo se změní web → hláška, nic se neuloží.

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

## Rozhodnutí Vítka (2026-11-21)

1. **Vzorek ruční kopie** pořídí Vítek podle návodu (viz níže).
2. **Ceny** přečteny z veřejných stránek produktů (licence Individual, ceník bez slevy). Uloží se do soukromého
   katalogu jako `price` u listingu na Cosmosu. Katalog musí `price` nově podporovat (zatím jen `ref` / `title`).
3. **Virtual Credits:** částka = `gross` i `net` (celé jako payout), měna USD.
4. **Refundy:** Refund Requests prohlédnuto (zatím prázdné, sloupce v ZDROJE). Zahrnou se do agenta, až bude vidět,
   jak se refund projeví.
5. **Playwright:** zatím nerozhodnuto, Vítek chce víc podrobností → `docs/spec/M4-prohlizec-moznosti.md`.

## Návod: vzorek ruční kopie

1. V Chromu otevři `publisher.leartesstudios.com/sales`.
2. Klikni kamkoli do stránky, **Ctrl+A** (označí celou stránku) a **Ctrl+C**.
3. Otevři Poznámkový blok a **Ctrl+V**.
4. V Cosmosu přejdi na stránku 2 tabulky, znovu Ctrl+A a Ctrl+C a v Poznámkovém bloku vlož na konec (Ctrl+End, Ctrl+V).
5. Ulož jako `data/private/cosmos/vzorek.txt` (kódování UTF-8, ve Windows 11 je výchozí).

Menu, záhlaví a patička stránky v textu nevadí, parser si najde jen tabulku.

## Mimo rozsah M4a

CGTrader (M4b), plánovač a denní běh (M5), automatické přihlašování (nikdy – přihlašuje se Vítek sám).
