# Zdroje dat

Co víme o každém marketplace. Doplňuj, když se něco ověří.

## Gumroad – API ✅

- REST API `https://api.gumroad.com/v2/`, autentizace access tokenem (hlavička `Authorization: Bearer …`).
- Token pro vlastní účet: Settings → Advanced → Applications → vytvořit aplikaci (Redirect URI libovolné,
  např. `http://localhost:8000/callback`) → **Generate access token**. Token nevyprší, dokud se nezruší.
- Prodeje: `GET /v2/sales`, filtry `after` / `before` (datum), stránkování přes `page_key` / `next_page_url`.
  Vyžaduje scope `view_sales`.
- Produkty: `GET /v2/products`.
- **K ověření v M1:** přesné názvy polí v odpovědi (cena, poplatek, měna, čas). Uložit jeden vzorek skutečné odpovědi
  do `data/private/` a podle něj napsat vymyšlený vzorek do `data/sample/`.

## Fab – měsíční CSV report 🟠

- Veřejné API není. Report se stahuje ručně v sekci prodejce (měsíčně).
- Sloupce (začátek, zbytek doplnit): `Day, Source, Listing Title, License, Base Price, Total VAT, Total Tax, Net Units, Net Sales, …`
- **K ověření v M3:** všechny sloupce, oddělovač, kódování, formát data a čísel, jak vypadá refund.
- Pozor: report je **agregovaný po dnech** (`Day`, `Net Units`), ne po transakcích. Unikátní klíč bude jiný
  než u ostatních (např. den + listing + licence + source).

## Cosmos (Leartes) – jen webová tabulka 🟠

- Sekce Reports → Sales. Žádný export.
- Sloupce: `Transaction ID` (např. `#30001`), `Products` (název + slug, např. `sample-medieval-village`),
  `Amount` (USD), `Payout` (USD), `Date` (`YYYY-MM-DD HH:MM`, časová zóna neznámá).
- Stránkování 10 / stránka.
- **K rozhodnutí v M4:** automatizace prohlížeče, nebo jestli web volá vlastní JSON API, které jde použít
  s Vítkovým přihlášením. Nejdřív se zeptat Vítka. Ověřit časovou zónu.

## CGTrader – API na žádost 🟡

- API přes OAuth 2.0, přístupový klíč se žádá formulářem na cgtrader.com/developers.
- Prodeje jsou v účtu v sekci My Sales (jednotlivé prodeje, měsíční statistiky, daně).
- **K ověření v M4:** jestli API vrací prodeje prodejce. Pokud ne, ruční export / web.
