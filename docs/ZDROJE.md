# Zdroje dat

Co víme o každém marketplace. Doplňuj, když se něco ověří.

## Gumroad – API ✅

- REST API `https://api.gumroad.com/v2/`, autentizace access tokenem (hlavička `Authorization: Bearer …`).
- Token pro vlastní účet: Settings → Advanced → Applications → vytvořit aplikaci (Redirect URI libovolné,
  např. `http://localhost:8000/callback`) → **Generate access token**. Token nevyprší, dokud se nezruší.
- Produkty: `GET /v2/products`.
- Výplaty: bankovní účet (IBAN) přes Gumroad, **výplata v CZK**. Prodeje a poplatky jsou ale v USD;
  převod na CZK dělá Gumroad při výplatě (kurz v API prodejů není).
- **Ověřeno 2026-11-20 (skutečné requesty):**
  - Hlavička `Authorization: Bearer <token>` funguje (HTTP 200). Dokumentace v příkladech posílá `access_token` jako parametr.
  - `GET /v2/sales` do 2026-11-20 vracel prázdný seznam (žádný prodej).
    Bez dalších stránek v odpovědi `next_page_url` / `next_page_key` vůbec nejsou.
  - `GET /v2/products`: 1 produkt, `price` je celé číslo v centech (`1499`), `currency` malými písmeny (`"usd"`),
    `sales_count` int, `sales_usd_cents` je **float** (do DB ne jako float).

### Ověřeno na skutečném (zkušebním) prodeji 2026-11-20

Vítek koupil vlastní produkt přes slevový kód (platba v CZK). Vzorek odpovědi: `data/private/gumroad_sample.json`.

- Struktura odpovídá dokumentaci níže: `price` int (150), `gumroad_fee` int, `created_at` `YYYY-MM-DDTHH:MM:SSZ`,
  `currency` `"usd"`, `refunded` / `partially_refunded` / `chargedback` jsou přítomné (bool).
- **Poplatek sedí se vzorcem** přímého prodeje: round(150 × 12,9 %) + 80 = **99** centů.
- `tax_cents` (32) je DPH navíc a **není v `price`**; Vítkův příjem se z ní nepočítá.
- Kupující platil v CZK → přišel `buyer_presentment` (`currency: "czk"`, `total_cents` včetně DPH, `fx_rate` jako text).
  Částky v USD (`price`, `gumroad_fee`) zůstávají kanonické.
- Navíc oproti ukázce v dokumentaci: `offer_code` (`code`, `name`, `displayed_amount_off`), `invoice_url`, `url_params`,
  `state`, `is_bundle_purchase`… – pro nás nepodstatné, zůstávají v `raw`.
- `product_id` prodeje = `id` produktu z `/v2/products` → vhodné jako `ref` v katalogu (M2).
- Bez dalších stránek `next_page_key` v odpovědi není (stránkování na skutečných datech zatím neověřeno – 1 prodej).
- Refund zatím neověřen.

### `GET /v2/sales` – podle dokumentace a zdrojového kódu

Vyžaduje scope `view_sales`.

Zdroj: Gumroad je open source (`github.com/antiwork/gumroad`, větev `main`, staženo 2026-11-20).
Stránka `gumroad.com/api` se skládá JavaScriptem a bez prohlížeče se nedá přečíst, proto jsme četli přímo zdroj:
`app/javascript/components/ApiDocumentation/Endpoints/Sales.tsx` + `responseFieldDefinitions.ts` (dokumentace)
a `app/controllers/api/v2/sales_controller.rb` + `Purchase#as_json` v `app/models/purchase.rb` (co se opravdu posílá).

- **Parametry:** `after`, `before` (`YYYY-MM-DD`; v kódu `created_at >= after`, `created_at < before`),
  `product_id`, `email`, `order_id`, `name`, `license_key`, `page_key`. Parametr `page` je zastaralý.
- **Stránkování:** max. **100** prodejů na stránku, od nejnovějšího. Když je další stránka, odpověď obsahuje
  `next_page_key` (např. `"20230119081040000000-123456"`) a `next_page_url`. Další stránka = stejný request + `page_key`.
  Na poslední stránce tato pole chybí.
- **Vrací jen „úspěšné“ prodeje** (popis endpointu). Jestli jsou mezi nimi i refundované, z kódu přímo nevyplývá
  (scope `for_sales_api`) → ověřit na prvním skutečném refundu.
- **Pole prodeje, která potřebujeme:**

| Pole | Typ | Význam |
|---|---|---|
| `id` | string | ID prodeje (např. `"B28UKN-dvxYabdavG97Y-Q=="`) → `external_id` |
| `order_id` | number | číselné ID objednávky |
| `created_at` | string | ISO 8601 v UTC (`"2021-01-05T19:38:56Z"`) → `sold_at` |
| `daystamp`, `timestamp` | string | jen pro zobrazení (čas v zóně prodejce, „about 2 months ago“) – **nepoužívat** |
| `product_id`, `product_permalink`, `product_name` | string | produkt |
| `price` | int | zaplaceno, **centy v USD** (kód: `price_cents`; dokumentace: „canonical fields like `price` keep their USD accounting meaning“) |
| `gumroad_fee` | int | poplatek Gumroadu v centech (USD) |
| `tax_cents`, `shipping_cents`, `tip_cents` | int | daň, doprava, spropitné v centech |
| `processor_fee_cents`, `processor_fee_currency` | int, string | jen u Stripe Connect / PayPal marketplace |
| `currency` | string | ISO kód měny, ve které je produkt **vypsaný** (`"usd"`) – malými písmeny |
| `currency_symbol`, `formatted_display_price`, `formatted_total_price` | string | texty pro zobrazení |
| `quantity` | int | počet kusů |
| `refunded` | bool | celý refund (**v ukázce v dokumentaci chybí, ale kód ho posílá**) |
| `partially_refunded` | bool | částečný refund |
| `amount_refundable_in_currency` | string | kolik ještě jde vrátit, **formátovaný text** v měně produktu (např. `"0"`, `"10"`) |
| `chargedback`, `disputed`, `dispute_won` | bool | chargeback / spor |
| `affiliate` | object | `{email, amount}`, `amount` je text (`"$2.50"`); chybí, když nebyl affiliate |
| `buyer_presentment` | object | jen když zákazník platil ve své měně (`currency`, `price_cents`, `total_cents`, `fx_rate` jako text, `refunded_cents`) – **není** to Vítkův příjem |
| `email`, `purchase_email`, `full_name`, `zip_code`, `country`… | | osobní údaje kupujícího – **neukládat mimo `raw`, nevypisovat** |

- **Pozor:** `Purchase#as_json` maže pole s hodnotou `null` (`delete_if { |_, v| v.nil? }`). Pole tedy může v odpovědi
  **úplně chybět**, ne být `null`. Parser musí počítat s chybějícími klíči.
- Částka refundu v centech v odpovědi přímo není. Dá se spočítat jako `price` − `amount_refundable_in_currency` (převedené
  na centy), ale jen u USD produktů. Pro M1 stačí `refunded` / `partially_refunded`.

## Fab – denní CSV report 🟠

- Veřejné API není. Report se stahuje ručně v sekci prodejce za libovolné období.
- **Ověřeno na skutečném souboru 2026-11-20** (leží v `data/private/fab/`, tady jen formát):
  - název `<od>_<do>_fab_daily_sales_report.csv`, UTF-8 bez BOM, čárka, CRLF, hlavička na 1. řádku,
  - přesně 9 sloupců: `Day, Source, Listing Title, License, Base Price, Total VAT, Total Tax, Net Units, Net Sales`,
  - `Day` = `YYYY-MM-DD` bez času a zóny (rozhodnutí Vítka: místní čas Europe/Prague),
  - částky s tečkou, bez pevného počtu desetin (`7.5`, `12.0`), max. 2 desetinná místa, bez měny,
  - `Net Sales = Base Price × Net Units`; `Net Units` může být > 1,
  - **refund = samostatný záporný řádek** v den refundu (`Net Units -1`, `Net Sales` záporné),
  - stejný listing má v různé dny různé `Base Price` (slevy),
  - `Source` zatím jen `Fab`, `License` `Personal` / `Professional`,
  - `Total VAT`, `Total Tax` jsou daně navíc, nejsou v `Net Sales`,
  - **poplatek Fabu v reportu není** (`Net Sales` je před poplatkem).
- Report je **agregovaný po dnech** (`Day`, `Net Units`), ne po transakcích. Klíč řádku: den + source + listing +
  licence + cena (návrh M3).
- Měna USD a podíl tvůrce 88 % potvrdil Vítek (2026-11-21); v reportu samotném nejsou.
- **Neověřeno:** jestli Fab zpětně mění už vydané dny (import by to zachytil jako `aktualizovaných`).

## Cosmos (Leartes) – jen webová tabulka 🟠

- Sekce Reports → Sales. Žádný export.
- Sloupce: `Transaction ID` (např. `#30001`), `Products` (název + slug, např. `sample-medieval-village`),
  `Amount` (USD), `Payout` (USD), `Date` (`YYYY-MM-DD HH:MM`, místní čas Vítka – Europe/Prague, tj. CET/CEST; rozhodnuto 2026-11-20).
- Stránkování 10 / stránka.
- **K rozhodnutí v M4:** automatizace prohlížeče, nebo jestli web volá vlastní JSON API, které jde použít
  s Vítkovým přihlášením. Nejdřív se zeptat Vítka.

## CGTrader – API na žádost 🟡

- API přes OAuth 2.0, přístupový klíč se žádá formulářem na cgtrader.com/developers.
- Prodeje jsou v účtu v sekci My Sales (jednotlivé prodeje, měsíční statistiky, daně).
- **K ověření v M4:** jestli API vrací prodeje prodejce. Pokud ne, ruční export / web.
