# Plán

| Milník | Co vznikne | Hotovo, když |
|---|---|---|
| **M0: Kostra** | repo, pravidla, plán, spec M1 | ✅ |
| **M1: Gumroad** | stažení prodejů přes API do SQLite | `uv run python -m sales_tracker sync gumroad` stáhne skutečné prodeje, druhé spuštění nepřidá duplicity, testy na ukázkových datech projdou |
| **M2: Katalog produktů** | `data/private/katalog.yaml` (Vítkovy produkty + jejich ID/názvy na každém marketplace), párování prodejů na produkt | každý prodej v DB má přiřazený produkt, nespárované se hlásí |
| **M3: Fab** | import měsíčních CSV reportů s validací | report se načte, vadné řádky se nahlásí, opakovaný import nevytvoří duplicity |
| **M4: Cosmos + CGTrader** | Cosmos z webu (po dohodě s Vítkem), CGTrader podle přístupu k API | prodeje z obou jsou v DB |
| **M5: Upozornění + týdenní agent** | denní běh (plánovač Windows), notifikace o novém prodeji, týdenní shrnutí od Claude | Vítek dostane shrnutí, ve kterém agent nic nevymýšlí (čísla sedí s DB) |
| **M6: Přehled** | jednoduchý dashboard (nejspíš Streamlit) | celkem / podle marketplace / podle produktu / v čase |
| **M7: Portfolio** | README, diagram, video, sekce „co jsem AI nepustil ven“ | připraveno k odeslání do přihlášky |

## Společný model prodeje (upřesněno v M1, 2026-11-20)

| Pole | Popis |
|---|---|
| `marketplace` | gumroad / fab / cgtrader / cosmos |
| `external_id` | ID transakce na marketplace (s `marketplace` tvoří unikátní klíč) |
| `product_title` | název produktu tak, jak ho uvádí marketplace |
| `product_ref` | ID / slug produktu na marketplace |
| `sold_at` | čas prodeje v UTC |
| `gross_cents` | cena, kterou zaplatil zákazník |
| `net_cents` | co dostane Vítek (po poplatcích), pokud je známo |
| `currency` | ISO kód měny (USD, EUR…), velkými písmeny. Částky se ukládají **v původní měně marketplace**, bez převodu |
| `status` | `sold` / `refunded` / `partially_refunded` / `chargeback`. Refund se neukládá jako nový prodej, jen změní `status` existujícího. Každý marketplace ho čte po svém |
| `raw` | původní záznam (JSON), kvůli dohledání |
