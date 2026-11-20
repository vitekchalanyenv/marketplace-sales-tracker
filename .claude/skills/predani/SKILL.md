---
name: predani
description: Předání práce na konci relace v projektu marketplace-sales-tracker. Použij, když Vítek řekne „předání“, „končíme“, „zapiš a pushni“ nebo spustí /predani.
---

# Předání relace

1. `git status --short`, `git log --oneline -10`.
2. `uv run pytest -q` a `uv run ruff check .`, výsledek zapiš přesně.
3. **Kontrola soukromí:** `git status` nesmí ukazovat nic z `data/private/`, `.env`, `.db` ani CSV mimo `data/sample/`.
   Když ano, zastav se a řekni to Vítkovi.
4. Aktualizuj `docs/PROGRESS.md` (napsáno / testy prošly / ověřeno na skutečných datech).
5. Chybovala AI v relaci? Doplň `docs/AI_CHYBY.md`. Když ne, nic nevymýšlej.
6. Přepiš celý `docs/HANDOFF.md` (datum, kde jsme, co dál, otevřené otázky).
7. Commit `Předání: <shrnutí>` s přípisem z pokynů systému, `git push`, ověř čistý `git status`.
8. Odpověz Vítkovi 3–5 řádky: hash, další krok, co od něj bude potřeba.
