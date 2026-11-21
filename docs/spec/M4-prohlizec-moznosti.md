# M4a: Možnosti automatického stahování z Cosmosu (podklad k rozhodnutí)

**Stav:** 2026-11-21 Vítek zvolil pokus s A. Pokus proběhl úspěšně, výsledky jsou na konci.

## Co o Cosmosu víme (průzkum 2026-11-21, jen čtení)

- Stránka `publisher.leartesstudios.com/sales` je aplikace v Next.js. HTML ze serveru je jen kostra,
  **tabulku plní JavaScript v prohlížeči**.
- Data bere z **neveřejného JSON API** `GET https://api.publisher.leartesstudios.com/sales?page=1&perPage=10`.
  (V prvním průzkumu jsem ho přehlédl, viz `AI_CHYBY.md`.)
- API **nepoužívá cookies**, ale **token v `localStorage`** prohlížeče. Bez tokenu vrací `401`.
  Strukturu odpovědi jsem nejdřív neověřil (ruční request s tokenem zablokovala bezpečnostní kontrola mého
  prostředí). Ověřil ji až pokus A, kde odpověď zachytí prohlížeč (viz níže).
- Přihlášení má **reCAPTCHA** (v prohlížeči je `_grecaptcha`), takže **automatické přihlašování nepřipadá v úvahu**.
  Přihlašuje se vždy Vítek ručně.
- Před webem je Cloudflare (`/cdn-cgi/rum`). Prohlížeč bez okna (headless) nebo čistě HTTP klient může narazit
  na ochranu proti botům. **Neověřeno.**
- Velikost stránky jde nastavit jen na 10, prodejů je zatím málo (2 stránky).

## Možnosti

### A) Playwright s vlastním profilem prohlížeče, čte JSON, který si stránka sama stáhne ⭐ doporučuji

- Python knihovna `playwright` ovládá prohlížeč. Spustí se s **vlastním trvalým profilem**
  (`data/private/browser/cosmos/`), do kterého se Vítek jednou přihlásí (`sync cosmos --login` otevře okno).
- Agent otevře `/sales` a **zachytí odpověď API**, kterou si stránka sama načte (`page.on("response")`).
  Dostane tak strukturovaný JSON. Token přitom nikdy nedrží náš kód, přihlášení řeší prohlížeč.
  Při změně vzhledu webu se nic nerozbije, rozbít to může jen změna API.
- Můžeme použít **nainstalovaný Chrome** (`channel="chrome"`), pak se nic dalšího nestahuje. Jinak se jednorázově
  stáhne Chromium od Playwrightu (desítky až stovky MB, přesnou velikost ověřím při instalaci).
- Proč ne tvůj běžný profil Chromu: novější Chrome podle mých znalostí nedovoluje automatizaci výchozího profilu
  (**z paměti, ověřím**) a mít oddělený profil je stejně bezpečnější.
- ✅ deterministické, zdarma, celé v repu (dobré do portfolia), funguje bez otevřeného Chromu
- ❌ nová závislost; když session vyprší, musí se Vítek znovu přihlásit (jak často, nevíme); Cloudflare a headless
  musíme vyzkoušet

### B) Přímé volání API z Pythonu (`httpx`) s tokenem v `.env`

- Nejlehčí, žádný prohlížeč. Vítek by ale musel ručně zkopírovat token z prohlížeče do `.env` a znovu pokaždé,
  když vyprší (platnost neznáme).
- ❌ ruční práce s tajným tokenem, neoficiální API, větší šance narazit na Cloudflare; nedoporučuji jako hlavní cestu

### C) Claude agent v tvém skutečném Chromu (Claude in Chrome) jako naplánovaná úloha

- Jednou denně spustí agenta, který v tvém přihlášeném Chromu otevře Sales, uloží text tabulky do
  `data/private/cosmos/` a pak běží **stejný deterministický import** jako u ruční kopie (čísla nepočítá AI).
- ✅ žádné další přihlašování, odolné vůči změnám vzhledu, „agent“ se hodí do příběhu projektu (M5)
- ❌ musí běžet počítač, Chrome i připojené rozšíření; každý běh stojí tokeny; méně předvídatelné než kód

### D) Ruční kopie tabulky (už rozhodnuto jako záložní cesta)

Vždy funguje a nic nepotřebuje. Viz `docs/spec/M4-cosmos.md`.

## Srovnání

| | A Playwright | B API + token | C Claude v Chromu | D ruční |
|---|---|---|---|---|
| Ruční práce | přihlášení občas | kopírování tokenu občas | žádná | pokaždé |
| Odolnost vůči změně webu | dobrá (čte API) | dobrá | nejlepší | – |
| Tajemství v projektu | žádné (session v profilu) | token v `.env` | žádné | žádné |
| Náklady | 0 | 0 | tokeny za každý běh | čas |
| Potřebuje běžící Chrome | ne | ne | ano | ano |
| Do portfolia | ✅ kód | ⚠️ | ✅ agent | – |

## Návrh dalšího kroku: krátký pokus (spike) s A

Hodinová ověřovačka, ne finální kód:
1. Nainstalovat `playwright`, spustit s `channel="chrome"` a vlastním profilem, Vítek se přihlásí.
2. Zjistit: zachytí se JSON z `/sales`? Jaká je jeho struktura (uloží se do `data/private/`)? Funguje headless
   přes Cloudflare? Vydrží přihlášení po restartu prohlížeče?
3. Podle výsledku: A jako hlavní cesta, nebo přejít na C.

Ruční kopie (D) se implementuje každopádně a sdílí s A/C převod a ukládání.

## Výsledek pokusu A (2026-11-21)

Skript `spikes/cosmos_playwright.py` (není produkční kód). Playwright 1.65 spouští **nainstalovaný Chrome**
(`channel="chrome"`), takže se žádné Chromium nestahuje. Samotný balíček `playwright` má ale ~113 MB (obsahuje Node.js).

| Otázka | Výsledek |
|---|---|
| Přihlášení ve vlastním profilu | ✅ Vítek se přihlásil v okně (reCAPTCHA ručně), skript nic nečetl |
| Vydrží login po zavření prohlížeče? | ✅ další běhy už přihlášené (jak dlouho vydrží dny/týdny, zatím nevíme) |
| Zachycení JSON z API stránky | ✅ odpověď `/sales?page=1&perPage=10` zachycena |
| Headless přes Cloudflare | ✅ funguje (1,5 s), stejná data jako s oknem |
| Token v našem kódu | ✅ nikde – přihlášení drží profil prohlížeče |

**Struktura odpovědi** (jen klíče; skutečný vzorek v `data/private/cosmos/`):

```
{ "data": [ { "id": int, "amount": str, "raw_amount": str, "type": "real" | "virtual",
              "created_at": str, "updated_at": str,
              "payout": { "amount": str, "currency": "USD" } | null,
              "refund_details": null | ?,
              "items": [ { "sku": str, "title": str, "type": str, "amount": str, "service": str,
                           "quantity": int, "license": "individual" | "studio" | "enterprise",
                           "promotions": [], "is_pre_order": bool } ] } ],
  "meta": { "total", "perPage", "currentPage", "lastPage", "firstPage",
            "firstPageUrl", "lastPageUrl", "nextPageUrl": "/?page=2", "previousPageUrl" } }
```

Zjištění, která mění návrh:
- **`items[].amount` = částka za každý produkt** a jejich součet přesně odpovídá `raw_amount` transakce (10 / 10).
  Hrubá tržba produktu se tedy nemusí odhadovat z ceníku. Rozdělit se musí jen `payout`, který je za celou
  transakci, a to nejlépe v poměru `items[].amount` (skutečně zaplacené ceny místo ceníku).
- `items[].sku` = slug (stejný jako v katalogu), `license` a `quantity` jsou k dispozici.
- `created_at` je ISO 8601 v **UTC** (`…THH:MM:SS.sssZ`). Tabulka na webu ukazuje stejný okamžik v Europe/Prague
  (o 1–2 h víc), což potvrzuje rozhodnutí o časové zóně u ruční kopie.
- Částky mají 4 desetinná místa (`"19.9000"`). U `type: "virtual"` je `amount` text s „Virtual Credits“,
  `raw_amount` číslo a `payout` = `null`.
- `refund_details` existuje (zatím vždy `null`) → refund půjde poznat, až nějaký bude.
- Stránkování: `meta.nextPageUrl`; další stránka = otevřít `/sales?page=N` a zachytit odpověď.

**Otevřené:** jak dlouho vydrží přihlášení; co přesně obsahuje `refund_details` při refundu.

**Doporučení:** cesta 2 = varianta A (Playwright, vlastní profil, headless, zachycení JSON). Ruční kopie zůstává jako
záložní cesta: tam se transakce s víc produkty dělí podle ceníku z katalogu, protože text tabulky částky za produkt nemá.
