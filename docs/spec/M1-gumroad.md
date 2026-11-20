# Specifikace M1: Stažení prodejů z Gumroadu

**Stav:** návrh, čeká na schválení Vítkem.

## Cíl

Příkaz `uv run python -m sales_tracker sync gumroad` stáhne prodeje z Gumroadu a uloží je do `data/private/sales.db`.

## Vstup

- `GUMROAD_ACCESS_TOKEN` z `.env`.
- Volitelně `--since YYYY-MM-DD`. Bez něj: od posledního uloženého prodeje z Gumroadu (první běh = vše).

## Chování

1. Načte token z `.env`. Když chybí, skončí srozumitelnou hláškou (bez tracebacku) a řekne, kde ho nastavit.
2. Stáhne prodeje přes `GET /v2/sales` se stránkováním, dokud jsou další stránky.
3. Každý prodej převede na společný model (viz `docs/PLAN.md`) a uloží. Původní záznam uloží do `raw`.
4. Prodej, který už v DB je (stejné `marketplace` + `external_id`), znovu nevloží. Pokud se změnil (např. refund), aktualizuje ho.
5. Na konci vypíše: kolik prodejů staženo, kolik nových, kolik aktualizovaných.

## Chyby

| Situace | Chování |
|---|---|
| chybí token | hláška „Chybí GUMROAD_ACCESS_TOKEN v .env“ |
| 401 / 403 | hláška „Token je neplatný nebo nemá oprávnění view_sales“ |
| výpadek sítě / 5xx | 3 pokusy s pauzou, pak hláška a konec bez poškození DB |
| neznámý formát záznamu | záznam se přeskočí, ale **vypíše se** (ID + důvod), nic tiše nezmizí |

## Testy (bez sítě)

- Převod vzorového záznamu z `data/sample/gumroad_sales.json` na společný model (cena v centech, čas v UTC, měna).
- Idempotence: uložení stejných prodejů dvakrát → v DB pořád stejný počet.
- Stránkování: dvě stránky ze vzoru → všechny prodeje.
- HTTP volání se v testech **mockuje**. Testy nesmí volat skutečné API ani potřebovat token.

## Před implementací ověřit

- [ ] Přesná struktura odpovědi `/v2/sales` (Vítek spustí jeden skutečný request, vzorek uloží do `data/private/gumroad_sample.json`).
- [ ] Podle něj vytvořit **vymyšlený** `data/sample/gumroad_sales.json` se stejnou strukturou (žádná skutečná jména, e-maily ani částky).
- [ ] Jak Gumroad značí refund.

## Mimo rozsah M1

Párování produktů (M2), notifikace (M5), dashboard (M6).
