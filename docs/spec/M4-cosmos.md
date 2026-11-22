# Specifikace M4a: Prodeje z Cosmosu (Leartes)

**Stav:** schváleno Vítkem 2026-11-21. **Cesta 1 (agent v prohlížeči): napsáno, testy prošly (196 celkem),
ověřeno na skutečném účtu** – všechny transakce, tržba i payout sedí na cent, druhý běh 0 nových a skončil na 1. stránce.
Cesta 2 (ruční kopie): doplněná část schválena Vítkem 2026-11-22.
CGTrader bude mít vlastní spec (M4b), až bude známý formát reportu z e-mailu, případně API.

## Cíl

Prodeje z Cosmosu se dostanou do `data/private/sales.db` **dvěma vyměnitelnými cestami** se společným jádrem:

1. **Agent v prohlížeči:** `sync cosmos` jednou denně sám načte prodeje ve vlastním přihlášeném profilu Chromu.
2. **Ruční kopie:** Vítek zkopíruje tabulku Reports → Sales do textového souboru a spustí `import cosmos` (záložní cesta).

Obě cesty vytvoří stejné `CosmosTransaction` a dál běží **stejný kód** (převod, rozdělení, uložení, párování).
Zdroj dat jde vyměnit, logika zůstává (ukázka modulárního návrhu do portfolia).

```
Playwright: zachycený JSON z API stránky ─► from_api() ───┐
                                                          ├─► CosmosTransaction ─► to_sales() ─► DB ─► párování
ruční kopie (.txt) ─► from_paste() (až bude vzorek) ──────┘
```

## Co víme o Cosmosu

Podrobně v `docs/ZDROJE.md` a `docs/spec/M4-prohlizec-moznosti.md` (pokus 2026-11-21). Shrnutí:
- Stránka `publisher.leartesstudios.com/sales` si data bere z `api.publisher.leartesstudios.com/sales?page=N&perPage=10`.
- Transakce: `id`, `type` (`real` / `virtual`), `raw_amount` (např. `"19.9000"`), `payout` (`{amount, currency}`
  nebo `null`), `created_at` (ISO 8601 UTC), `refund_details` (`null`, formát při refundu neznámý) a `items[]`
  (`sku` = slug, `title`, `amount` = částka za produkt, `quantity`, `license`).
- Součet `items[].amount` = `raw_amount` (ověřeno 10 z 10). `payout` je jen za celou transakci.

## Společné jádro (`cosmos.py`)

**`CosmosTransaction`:** `id`, `created_at` (UTC), `virtual` (bool), `amount_cents`, `payout_cents` (nebo `None`),
`refunded` (bool), `items` (`sku`, `title`, `amount_cents` nebo `None`, `quantity`, `license`), `source` (`browser` / `paste`).

**Převod na záznamy v `sales`:** jeden záznam **na každý produkt v transakci**.

| Společný model | Cosmos | Poznámka |
|---|---|---|
| `external_id` | `<id>\|<sku>` | např. `20001\|sample-medieval-village` |
| `product_ref` | `sku` (slug) | párování přes `ref` v katalogu |
| `product_title` | `items[].title` | |
| `sold_at` | `created_at` (UTC) | ruční kopie: `Date` v Europe/Prague → UTC |
| `quantity` | `items[].quantity` | |
| `gross_cents` | `items[].amount` | ruční kopie: dělení podle ceníku z katalogu |
| `net_cents` | `payout` rozdělený v poměru `gross_cents` produktů | Virtual Credits: `net = gross` |
| `currency` | `USD` | i Virtual Credits (rozhodnutí Vítka) |
| `status` | `refunded`, když `refund_details` není `null`, jinak `sold` | formát refundu neověřen → upozornění |
| `raw` | celá transakce z API + `source` + index produktu | bez osobních údajů (API je neposílá) |

**Dělení payoutu (rozhodnutí Vítka 2026-11-21: podle skutečně zaplacených částek):**
- Podíl produktu = `items[].amount` / `raw_amount`. Centy se rozdělí metodou největšího zbytku, takže
  **součet částí je vždy přesně celý payout**.
- Když jsou všechny částky produktů 0 (např. zdarma), payout se dělí rovným dílem.

**Peníze:** `Decimal` z textu, na centy. Částka s nenulovou třetí nebo čtvrtou desetinou (`"19.9050"`) se
**nezaokrouhluje**: transakce se přeskočí a vypíše (zatím jsme takovou neviděli).

**Validace transakce** (chyba → přeskočí se a vypíše ID + důvod): chybí `id` / `created_at` / `items`, neznámý
`type`, `payout` u `real` chybí nebo není v USD, `sku` se v transakci opakuje, `quantity` < 1, součet
`items[].amount` ≠ `raw_amount`.

**Idempotence:** klíč `(cosmos, id|sku)`. Agent i ruční kopie můžou stejné prodeje načíst opakovaně.

## Cesta 1: agent v prohlížeči – `sync cosmos` (`cosmos_browser.py`)

- Playwright s **nainstalovaným Chrome** (`channel="chrome"`) a **vlastním trvalým profilem**
  `data/private/browser/cosmos/` (mimo git). Headless.
- `sync cosmos --login`: otevře okno, Vítek se přihlásí sám (reCAPTCHA), skript čeká, až stránka načte prodeje.
  Heslo ani token neprochází naším kódem, `.env` ani logem.
- `sync cosmos`: otevře `/sales?page=1`, zachytí odpověď API (`page.on("response")`) a pokračuje na
  `/sales?page=N`, dokud:
  - není poslední stránka (`meta.lastPage`), nebo
  - **všechny transakce na stránce už jsou v DB** a od nejstarší z nich uplynulo víc než 30 dní
    (stejné okno pro refundy jako u Gumroadu). První běh projde všechno.
  - Mezi stránkami pauza 3 s. Nejvýš 50 stránek (pojistka).
- Session vypršela (API nevrátí 200 nebo stránka skončí jinde než na `/sales`) → hláška
  „přihlas se: sync cosmos --login“, **nic se neuloží**.
- Odpověď nemá očekávaný tvar → hláška + screenshot do `data/private/cosmos/`, nic se neuloží.
- Logika stránkování je oddělená od Playwrightu (`fetch_pages(load_page, …)`) a testuje se bez prohlížeče.

## Cesta 2: ruční kopie – `import cosmos [soubor]`

**Formát podle skutečného vzorku (2026-11-22, 2 stránky; porovnáno s daty z API). Příklady níže jsou vymyšlené,
skutečný vzorek je jen v `data/private/`, vymyšlený v `data/sample/cosmos_paste.txt`:**

```
#30005	                                 ← "#" + ID transakce (stejné ID jako v API), za ním tabulátor
Medieval Village Environment             ← název produktu
sample-medieval-village                  ← sku (slug); dvojice název + sku se opakuje pro každý produkt
19.90 USD	17.41 USD	2026-01-20 23:30  ← Amount, Payout, Date (oddělené tabulátorem)
```

- Virtual Credits: `9.90	Virtual Credits	2026-01-10 12:00` (částka bez měny, místo payoutu text).
- `Date` je **místní čas (Europe/Prague) na minuty**, bez sekund. Ověřeno na skutečných transakcích v zimním
  i letním čase proti `created_at` z API.
- Menu, záhlaví (jméno a e-mail účtu), `10 / Page`, `Total: N` a patička se ignorují. Parser bere jen bloky
  od řádku `#ID` po řádek s částkami a datem.
- V textu **není** množství, licence, částka za produkt ani refund.

**Převod:**
- Stejné `CosmosTransaction` jako z API (`source = "paste"`), `quantity = 1`, `refunded = False`.
- Transakce s jedním produktem: částka produktu = celá `Amount`.
- Víc produktů: `Amount` se rozdělí podle `price` listingu Cosmosu v katalogu (centy metodou největšího zbytku,
  součet sedí přesně). Je to **odhad**: skutečné částky se liší podle licence a slevy. U jediné takové skutečné
  transakce (licence Enterprise) se odhad lišil o 2 centy na produkt, součet přesně. Když některá cena
  v katalogu chybí, transakce se přeskočí a vypíše.
- `raw` = jen rozparsovaná pole a zdroj, **ne celý vložený text**. V textu je i jméno a e-mail účtu.

**Souběh s agentem (schváleno):** když už je transakce v DB (podle ID), ruční kopie ji **nemění** a vypíše
„už v DB, přeskočeno“. Data z API jsou přesnější: sekundy, skutečné částky produktů, licence, množství a refund.
Ruční kopie tak jen doplní transakce, které agent nestáhl.

**Katalog:** u listingu Cosmosu přibude volitelné `price` (částka v USD, např. `19.90`). Platí jen pro dělení
v ruční kopii, jinde se nepoužije.

**Příkaz:** `import cosmos [soubor]`, bez cesty `data/private/cosmos/*.txt`. Denní agent ho nespouští, protože
ruční kopie je záložní cesta pro chvíle, kdy agent nejede.

## Výpis

`Cosmos (prohlížeč): transakcí N, záznamů M, nových, aktualizovaných, přeskočeno`, pak párování s katalogem.

## Testy (bez sítě a bez prohlížeče, vymyšlená data `data/sample/cosmos_api_page*.json`)

- `from_api`: běžná transakce, víc produktů, Virtual Credits, refund, licence; všechny chyby z Validace.
- `to_sales`: dělení payoutu na cent (i nedělitelné částky), částky v centech jako `int`, UTC, idempotence v DB.
- `fetch_pages`: první běh projde všechny stránky; další běh skončí na stránce, kde je vše známé a starší než 30 dní;
  pauzy; pojistka 50 stránek; neplatná odpověď.
- CLI: výpis, session vypršela → nic se neuloží, párování po importu.
- Ostrý běh proti webu se ověřuje ručně (spike i `sync cosmos`).

## Rozhodnutí Vítka (2026-11-21)

1. Vzorek ruční kopie pořídí Vítek podle návodu.
2. Ceny produktů na Cosmosu (pro ruční kopii) přečteny z veřejných stránek; do katalogu jako `price` u cesty 2.
3. **Virtual Credits:** částka = `gross` i `net`, měna USD.
4. **Refundy:** zahrnout do agenta (`refund_details`), formát ověřit při prvním refundu.
5. **Playwright** jako automat (pokus úspěšný), **payout dělit podle skutečných částek produktů** (ne ceníku).

## Návod: vzorek ruční kopie

1. V Chromu otevři `publisher.leartesstudios.com/sales`.
2. Klikni kamkoli do stránky, **Ctrl+A** (označí celou stránku) a **Ctrl+C**.
3. Otevři Poznámkový blok a **Ctrl+V**.
4. V Cosmosu přejdi na stránku 2 tabulky, znovu Ctrl+A a Ctrl+C a v Poznámkovém bloku vlož na konec (Ctrl+End, Ctrl+V).
5. Ulož jako `data/private/cosmos/vzorek.txt` (kódování UTF-8, ve Windows 11 je výchozí).

Menu, záhlaví a patička stránky v textu nevadí, parser si najde jen tabulku.

## Mimo rozsah M4a

CGTrader (M4b), plánovač a denní běh (M5), automatické přihlašování (nikdy – přihlašuje se Vítek sám).
