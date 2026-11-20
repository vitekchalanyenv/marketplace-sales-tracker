# marketplace-sales-tracker – pokyny pro Claude Code

Vítek prodává 3D assety (prostředí pro hry) na několika marketplaces: **Gumroad, Fab, CGTrader, Cosmos (Leartes)**.
Tenhle nástroj stahuje jeho prodeje ze všech zdrojů do jedné lokální databáze, páruje stejné produkty napříč
platformami, upozorní na nový prodej a jednou týdně napíše shrnutí.

Je to **reálný nástroj pro Vítka** a zároveň **portfolio** (multikanálový e-commerce: různé zdroje, různé formáty,
párování produktů, plánovaný agent). Komunikace **česky**, kód a názvy v kódu anglicky, README anglicky,
interní dokumentace česky.

## Než začneš

1. `docs/HANDOFF.md` – předání z minulé relace (`/navazani`, na konci `/predani`).
2. `docs/PROGRESS.md` – stav milníků.
3. `docs/PLAN.md` – milníky a kritéria hotovosti.
4. `docs/ZDROJE.md` – co víme o každém marketplace (přístup, formát, sloupce).
5. Specifikace aktuálního milníku v `docs/spec/`.

## Jak pracujeme (AI-first)

Kód píšeš ty (agent). Vítek zadává, kontroluje, spouští a rozhoduje. Na rozdíl od učebního projektu
`eshop-pohoda-most` tady **nemusíš vysvětlovat každý krok**, ale:

1. **Specifikace → testy → kód.** Každý milník má spec v `docs/spec/`. Než začneš kódovat, ověř, že spec existuje
   a Vítek ji schválil. Testy píšeš ty, ale Vítek je musí umět přečíst.
2. **Malé commity**, ve tvaru `M1: stahování prodejů z Gumroadu`.
3. **Nevymýšlej API.** Formát odpovědí a názvy polí ověř na dokumentaci nebo skutečné odpovědi, ne z paměti.
   Když si nejsi jistý, napiš to a navrhni ověření (jeden testovací request a uložení vzorku).
4. **Po každém milníku** krátké shrnutí pro Vítka: co vzniklo, jak to ověřit, co zůstalo otevřené.
5. **Zapisuj vlastní chyby** do `docs/AI_CHYBY.md` (co jsi navrhl špatně, jak se to poznalo, jak opraveno).
   Je to sekce portfolia „co jsem AI nepustil ven“. Nevynechávej to.

## Prostředí

- Windows, PowerShell. Python 3.12+ přes **uv**: `uv sync`, `uv run pytest`, `uv run ruff check .`
- Kód v `src/sales_tracker/`, testy v `tests/`.
- Lokální databáze: SQLite v `data/private/sales.db`.

## Zlatá pravidla

1. **Skutečná data nikdy do gitu.** Prodeje, reporty, databáze a vzorky skutečných odpovědí patří do `data/private/`
   (je v `.gitignore`). Do repa jen **vymyšlená** ukázková data v `data/sample/`. Před každým commitem zkontroluj
   `git status`, že tam není nic z `data/private/` ani `.db`/`.csv` mimo `data/sample/`.
2. **Tajemství jen v `.env`.** Tokeny a hesla nikdy v kódu, logu, testu ani commitu. Vzor v `.env.example`.
   Tokeny nevypisuj ani zkráceně.
3. **Idempotence.** Stažení stejných dat dvakrát nesmí vytvořit duplicitní prodej. Klíč prodeje = (marketplace, ID transakce).
4. **„Napsáno ≠ funguje.“** Stav piš přesně: napsáno / testy prošly / ověřeno na skutečných datech.
5. **Peníze jako celá čísla v centech** (nebo `Decimal`), nikdy `float`. Vždy s měnou.
6. **Čas v UTC** v databázi, převod na místní čas až při zobrazení.
7. **Šetrně k webům.** Kde není API (Cosmos, Fab), žádné agresivní scrapování: jednou denně, s pauzami, jen Vítkův účet.
   Než začneš automatizovat prohlížeč, zeptej se Vítka.
8. **Rozpor nerozhoduj sám.** Zeptej se a zapiš do `PROGRESS.md`.
