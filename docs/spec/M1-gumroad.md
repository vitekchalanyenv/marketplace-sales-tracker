# Specifikace M1: Stažení prodejů z Gumroadu

**Stav:** schváleno Vítkem 2026-11-20. Upřesněno 2026-11-20 podle dokumentace a zdrojového kódu Gumroadu
(skutečný prodej zatím neexistuje). Otázky 1–3 rozhodl Vítek 2026-11-20.
**Implementace:** napsáno, testy prošly (64), ověřeno na skutečném účtu – ale jen s 0 prodeji (viz `PROGRESS.md`).

## Cíl

Příkaz `uv run python -m sales_tracker sync gumroad` stáhne prodeje z Gumroadu a uloží je do `data/private/sales.db`.

## Vstup

- `GUMROAD_ACCESS_TOKEN` z `.env`.
- Volitelně `--since YYYY-MM-DD`. Bez něj: posledních 30 dní (kvůli refundům starších prodejů); první běh (prázdná DB) = vše.

## Chování

1. Načte token z `.env`. Když chybí, skončí srozumitelnou hláškou (bez tracebacku) a řekne, kde ho nastavit.
2. Stáhne prodeje přes `GET /v2/sales` (hlavička `Authorization: Bearer`). Další stránky: opakuje request
   s `page_key` = `next_page_key` z předchozí odpovědi, dokud `next_page_key` v odpovědi je. Mezi stránkami krátká pauza.
   S `--since` posílá `after=YYYY-MM-DD`. Bez `--since` a s prodeji v DB: `after` = dnes − 30 dní (UTC).
   Už uložené prodeje se tím stáhnou znovu; idempotence zajistí, že nevzniknou duplicity, a změněný `status` se aktualizuje.
3. Každý prodej převede na společný model (viz `docs/PLAN.md`) a uloží. Původní záznam uloží do `raw`.
4. Prodej, který už v DB je (stejné `marketplace` + `external_id`), znovu nevloží. Pokud se změnil (např. refund), aktualizuje ho.
5. Na konci vypíše: kolik prodejů staženo, kolik nových, kolik aktualizovaných.

## Mapování na společný model

Podle `docs/ZDROJE.md` (sekce Gumroad). Klíče, které v odpovědi chybí, se berou jako „neznámé“, ne jako chyba
(Gumroad pole s hodnotou `null` vůbec neposílá).

| Společný model | Gumroad | Poznámka |
|---|---|---|
| `marketplace` | `"gumroad"` | |
| `external_id` | `id` | povinné; bez něj se záznam přeskočí a vypíše |
| `product_title` | `product_name` | |
| `product_ref` | `product_id` | `product_permalink` zůstane v `raw` |
| `sold_at` | `created_at` | ISO 8601, převést na UTC `datetime`; povinné |
| `gross_cents` | `price` | celé číslo, centy USD; povinné |
| `net_cents` | `price − gumroad_fee` | `gumroad_fee` obsahuje Gumroad fee **i** processing fee (viz níže) |
| `currency` | `"USD"` | `price` a `gumroad_fee` jsou podle dokumentace i kódu vždy v USD; `currency` z odpovědi (měna, ve které je produkt vypsaný) zůstane v `raw` |
| `status` | `chargedback` → `chargeback`, jinak `refunded` → `refunded`, jinak `partially_refunded` → `partially_refunded`, jinak `sold` | chybějící pole = `false` |
| `raw` | celý záznam | obsahuje osobní údaje kupujícího → jen v lokální DB, nikdy ve výpisu ani v logu |

`daystamp` a `timestamp` se **nepoužívají** (texty pro zobrazení v zóně prodejce). `buyer_presentment` (platba v měně
kupujícího) se nepoužívá pro částky, jen zůstane v `raw`.

### Poplatky Gumroadu (ověřeno v kódu, sedí s nastavením Vítkova účtu)

Vítek dostává výplaty na bankovní účet přes Gumroad (ne vlastní Stripe), takže platby jdou přes Gumroad merchant
account a `gumroad_fee` = Gumroad fee + processing fee:

- přímý prodej: 10 % + 50 ¢ + 2,9 % + 30 ¢ (např. $14.99 → 193 + 80 = **273** centů),
- prodej přes Discover: 30 % včetně processingu, bez fixní části (`discover_fee_charged: true`; $29.99 → **900** centů),
- prodej zdarma: 0.

Zdroj: `Purchase#calculate_fees` v `app/models/purchase.rb` (konstanty `GUMROAD_FLAT_FEE_PER_THOUSAND = 100`,
`PROCESSOR_FEE_PER_THOUSAND = 29`, `PROCESSOR_FIXED_FEE_CENTS = 30`, `GUMROAD_DISCOVER_FEE_PER_THOUSAND = 300`).
Provize affiliate v `gumroad_fee` **není**. Vítek affiliate nepoužívá; když se v záznamu objeví `affiliate`,
sync vypíše upozornění (ID prodeje), že `net_cents` je nadhodnocený.

## Rozhodnutí Vítka (2026-11-20)

1. **Stav prodeje:** do společného modelu přibývá `status`; refund může nastat u všech marketplaces, každý ho čte po svém.
   Gumroad: bez `--since` se stahuje posledních 30 dní.
2. **Čistý příjem:** `price − gumroad_fee` (viz poplatky výše).
3. **Měna:** každý prodej se ukládá v původní měně marketplace (Gumroad = USD). Převod mezi měnami se v DB nedělá;
   kam a podle jakých kurzů převádět pro shrnutí, se rozhodne v milníku se shrnutím (viz `PROGRESS.md`).

## Chyby

| Situace | Chování |
|---|---|
| chybí token | hláška „Chybí GUMROAD_ACCESS_TOKEN v .env“ |
| 401 / 403 | hláška „Token je neplatný nebo nemá oprávnění view_sales“ |
| výpadek sítě / 5xx | 3 pokusy s pauzou, pak hláška a konec bez poškození DB |
| neznámý formát záznamu | záznam se přeskočí, ale **vypíše se** (ID + důvod), nic tiše nezmizí |

## Testy (bez sítě)

- Převod vzorového záznamu z `data/sample/gumroad_sales.json` na společný model (cena v centech, čas v UTC, měna).
- Refund, částečný refund a záznam s chybějícími volitelnými poli (`tax_cents`, `affiliate`…) ze vzorku.
- `status` podle tabulky; `net_cents` = `price − gumroad_fee`; záznam s `affiliate` → upozornění.
- Bez `--since` s neprázdnou DB → `after` = dnes − 30 dní.
- Záznam bez `id` nebo `created_at` se přeskočí a vypíše, ostatní se uloží.
- Idempotence: uložení stejných prodejů dvakrát → v DB pořád stejný počet.
- Stránkování: `gumroad_sales.json` (má `next_page_key`) + `gumroad_sales_page2.json` (nemá) → 5 prodejů, druhý request s `page_key`.
- HTTP volání se v testech **mockuje**. Testy nesmí volat skutečné API ani potřebovat token.

## Před implementací ověřit

- [x] Struktura odpovědi `/v2/sales`: z dokumentace a zdrojového kódu Gumroadu (viz `docs/ZDROJE.md`).
  Skutečný request 2026-11-20 vrátil prázdný seznam (žádný prodej). **Na skutečném prodeji neověřeno.**
- [x] Vymyšlený vzorek: `data/sample/gumroad_sales.json` + `gumroad_sales_page2.json`.
- [x] Refund: pole `refunded` / `partially_refunded` (bool). Jestli API vrací i plně refundované prodeje, ověřit na
  prvním skutečném refundu.
- [x] Vítek rozhodl otázky 1–3 (2026-11-20).

## Mimo rozsah M1

Párování produktů (M2), notifikace (M5), dashboard (M6).
