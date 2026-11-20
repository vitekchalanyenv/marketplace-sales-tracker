# Specifikace M2: Katalog produktů a párování prodejů

**Stav:** návrh 2026-11-20, čeká na schválení Vítkem (a odpovědi na otázky na konci).

## Cíl

Jeden asset (např. „Medieval Village“) se na každém marketplace jmenuje a identifikuje jinak.
Katalog říká, které listingy na kterých marketplaces jsou **tentýž produkt**, a každý prodej v DB se podle něj
přiřadí k produktu. Díky tomu půjde později říct „kolik vydělal produkt X celkem“.

## Jak marketplaces produkt označují (z `docs/ZDROJE.md`)

| Marketplace | Co máme v prodeji | Stálé ID? |
|---|---|---|
| Gumroad | `product_id` (např. `"32-nPainqpLj1B_WIwVlMw=="` z dokumentace), `product_name`, `product_permalink` | ano (`product_id`) |
| Fab | jen `Listing Title` (+ `License`) | **ne**, jen název |
| Cosmos | `Products` = název + slug (např. `sample-medieval-village`) | slug (asi stálý) |
| CGTrader | zatím nevíme (M4) | ? |

Proto se listing v katalogu dá popsat **ID/slugem** (`ref`), **přesným názvem** (`title`), nebo obojím.

## Katalog: `data/private/katalog.yaml`

Píše ho Vítek ručně (s pomocí výpisu nespárovaných prodejů, viz níže). Je v `data/private/` jako ostatní skutečná data;
v repu je jen vymyšlený `data/sample/katalog.yaml`.

```yaml
products:
  - key: medieval-village               # stálý krátký klíč produktu (malá písmena, číslice, pomlčky)
    name: Medieval Village Environment  # jak ho chce vidět Vítek v přehledech
    listings:
      gumroad:
        - ref: "SAMPLE-prod-medieval-village=="
      fab:
        - title: "Medieval Village Environment - UE5"
        - title: "Medieval Village (old listing)"
      cosmos:
        - ref: sample-medieval-village
  - key: scifi-hangar
    name: Sci-Fi Hangar Environment
    listings:
      gumroad:
        - ref: "SAMPLE-prod-scifi-hangar=="
```

- Jeden produkt může mít na jednom marketplace **víc listingů** (např. starý a nový název na Fabu, samostatná verze).
- Listing musí mít `ref`, `title`, nebo obojí.

## Párování

Pro každý prodej (v pořadí):

1. **Podle `ref`:** `product_ref` prodeje == `ref` listingu na stejném marketplace.
2. **Podle `title`:** `product_title` prodeje == `title` listingu na stejném marketplace, po normalizaci:
   malá písmena, ořezané a sloučené mezery. Nic dalšího (žádné „podobné“ názvy).
3. Jinak je prodej **nespárovaný**.

**Žádné automatické párování podle podobnosti.** Podobnost se použije jen jako *návrh* ve výpisu nespárovaných;
rozhoduje Vítek zápisem do katalogu. Důvod: špatně přiřazený prodej by tiše zkreslil čísla.

Výsledek se uloží do nového sloupce `sales.product_key` (NULL = nespárovaný). Párování se spustí:
- automaticky na konci každého `sync`,
- ručně příkazem `catalog match` (po úpravě katalogu), který přepočítá **všechny** prodeje.

## Příkazy

- `uv run python -m sales_tracker catalog check`
  - zkontroluje katalog (viz Validace) a vypíše chyby s číslem řádku/produktem,
  - vypíše **nespárované prodeje seskupené po listingu**: marketplace, `ref`, `title`, počet prodejů, a když existuje,
    návrh nejpodobnějšího produktu z katalogu („možná: medieval-village?“), plus hotový úryvek YAML k vložení.
- `uv run python -m sales_tracker catalog match` – přepočítá `product_key` u všech prodejů, vypíše: spárováno X,
  nespárováno Y (a seznam jako `check`).

## Validace katalogu (chyba = nic se nepřepočítá)

| Situace | Chování |
|---|---|
| soubor chybí | hláška, kde ho založit, a odkaz na `data/sample/katalog.yaml`; `sync` funguje dál, jen nepáruje |
| neplatné YAML | hláška s číslem řádku |
| chybí `key` / `name`, nebo `key` není ve tvaru `a-z0-9-` | chyba u daného produktu |
| duplicitní `key` | chyba |
| neznámý marketplace (překlep `gumraod`) | chyba |
| listing bez `ref` i `title` | chyba |
| stejný `ref` nebo stejný normalizovaný `title` na jednom marketplace u **dvou produktů** | chyba (párování by nebylo jednoznačné) |

## Testy (bez sítě, vymyšlená data)

- Načtení `data/sample/katalog.yaml`, všechny chyby z tabulky Validace.
- Párování podle `ref`, podle `title` (velikost písmen, mezery), `ref` má přednost, nespárovaný prodej.
- Prodej z jiného marketplace se stejným názvem se nespáruje s listingem jiného marketplace.
- `catalog match` po úpravě katalogu změní `product_key` (i zpět na NULL, když listing z katalogu zmizí).
- Výpis nespárovaných: seskupení, počty, návrh podle podobnosti, žádné osobní údaje.
- `sync` bez katalogu projde a vypíše upozornění.

## Hotovo, když

- testy projdou,
- Vítek založí skutečný `data/private/katalog.yaml` a `catalog check` na něm projde bez chyb,
- každý prodej v DB má `product_key`, nespárované se hlásí. **Pozor:** v DB je teď 0 prodejů (Gumroad), takže na
  skutečných prodejích se párování ověří až s M3 (Fab) / M4 (Cosmos, CGTrader).

## Nová závislost

`pyyaml` (čtení YAML). Alternativa bez závislosti by byl TOML (`tomllib` je ve standardní knihovně), ale `PLAN.md`
počítá s YAML a ten se ručně píše pohodlněji.

## K rozhodnutí (Vítek)

1. **Co je „jeden produkt“?** Když prodáváš stejné prostředí jako UE projekt a zvlášť třeba jako Unity / FBX verzi,
   je to jeden produkt (víc listingů), nebo dva?
2. **Balíčky (bundles):** prodáváš někde balíček víc prostředí? Návrh pro M2: balíček = samostatný produkt v katalogu
   (rozpočítání tržby na jednotlivé produkty až někdy později, pokud vůbec).
3. **Seznam produktů:** pošleš seznam svých produktů a jejich názvy / odkazy na jednotlivých marketplaces? Gumroad můžu
   načíst sám přes API (`/v2/products`, 1 produkt), ostatní zatím ne.

## Mimo rozsah M2

Import Fab (M3), Cosmos a CGTrader (M4), přehledy podle produktu (M6), rozpočítání balíčků.
