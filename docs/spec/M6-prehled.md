# Specifikace M6: přehled prodejů (dashboard)

**Stav:** schváleno Vítkem 2026-11-23. Napsáno, testy prošly; ověřeno na skutečných datech (součty tento měsíc
po marketplacech v kusech, měně i Kč sedí s výpočtem ranního e-mailu, kurzy doplněny bez chyby, stránka se vykreslí).
Vítek zkontroloval v prohlížeči 2026-11-23.

## Cíl

Jedna lokální stránka, kde je vidět, kolik se prodalo celkem, na kterém marketplace, který produkt a jak se to vyvíjí
v čase. Ranní e-mail říká „co je nového“, přehled říká „jak si stojím“.

## Rozhodnutí Vítka (2026-11-23)

1. **Streamlit** (interaktivní stránka s filtry).
2. Obsah podle bodů 1–5 níže.
3. Částky **v původní měně (USD/EUR) a k tomu přepočet na Kč**.

## Spuštění

- `uv run python -m sales_tracker dashboard` spustí Streamlit a otevře prohlížeč na `localhost`.
  Běží, dokud je otevřený terminál (Ctrl+C ukončí).
- Server poslouchá **jen na 127.0.0.1** a bez odesílání statistik o používání Streamlitu (`server.address`,
  `browser.gatherUsageStats`, ověřeno v nainstalovaném Streamlitu 1.67: statistiky jsou ve výchozím stavu zapnuté).
  Bez tlačítka „Deploy“ (`client.toolbarMode minimal`).
- Streamlit běží `server.headless` a prohlížeč otevře náš příkaz: jinak se při prvním spuštění v terminálu ptá na
  e-mail pro newsletter a čeká na odpověď (zjištěno při ostrém spuštění).
- Čte `data/private/sales.db`. Prodeje **jen čte**, nic nemění. Jediný zápis jsou chybějící kurzy ČNB do
  `fx_rates` (stejná cache jako u e-mailu).
- `uv run python -m sales_tracker demo --dashboard` spustí totéž na vymyšlených datech z `data/sample/`
  (dočasná DB, vymyšlené kurzy, pevné „dnes“). Z toho vznikne screenshot do README.

## Pravidla pro čísla (stejná jako v e-mailu)

- Vyloučené prodeje (`exclude`, zkušební nákup) se nepočítají nikde.
- Částka = čistý příjem (`net_cents`). Vrácení snižuje součty stejně jako v e-mailu.
- Kusy = součet `quantity` (vrácené kusy záporně).
- Kč = kurz ČNB **ke dni prodeje** (místní datum), zaokrouhlení ROUND_HALF_UP, stejný kód jako v e-mailu.
- Součty v původní měně se **nesčítají přes měny**: „45,90 USD + 12,00 EUR (≈ 1 323,15 Kč)“.
- Čas se zobrazuje v místním čase (Europe/Prague). Fab a CGTrader jen datum, bez hodiny (jako v e-mailu).
- Výpočty jsou v samostatném modulu bez Streamlitu (`overview.py`), stránka je jen vykreslí. Díky tomu jdou
  otestovat bez prohlížeče a e-mail i přehled počítají stejně.

### Kurzy pro starší prodeje

- E-mail zatím stahoval kurzy jen pro dny, které zobrazoval. Přehled potřebuje kurz pro **každý den s prodejem**.
  V cache jsou zatím jen dny zobrazené v e-mailech, takže první otevření jich pár desítek stáhne.
- Chybějící dny se stáhnou **při prvním otevření**, po jednom, s pauzou 1 s mezi requesty (šetrně k ČNB).
  Pak jsou v cache natrvalo.
- Když ČNB nejde stáhnout: částky v původní měně zůstanou, Kč u dotčených prodejů chybí a stránka nahoře
  napíše „Kurz ČNB nedostupný, součty v Kč nejsou úplné“. Nikdy se nezobrazí neúplný součet v Kč, jako by byl celý.

## Obsah stránky

1. **Čísla nahoře:** tento měsíc, minulý měsíc, letošek celkem. U každého čistý příjem v původní měně a v Kč
   a počet kusů. Pod tím rozpad podle marketplace (stejná tři období).
2. **Graf v čase:** čistý příjem v Kč po měsících, sloupce rozdělené barvou podle marketplace. Jak přesně
   Streamlit kreslí skládaný sloupcový graf, ověřím v jeho dokumentaci.
3. **Produkty napříč platformami:** jeden řádek na produkt z katalogu. Sloupce: název z katalogu, kusy celkem,
   příjem v Kč, příjem v původní měně, na kterých marketplaces se prodává (s kusy u každého).
   Řazeno podle příjmu v Kč. Nespárované prodeje mají vlastní řádky „nespárováno: <název z marketplace>“,
   aby se nic neztratilo a bylo vidět, co doplnit do katalogu.
4. **Filtry** (v postranním panelu):
   - **Období:** tento měsíc, minulý měsíc, letos, posledních 12 měsíců, vše, vlastní rozsah od–do.
   - **Marketplace:** výběr jednoho nebo více.

   Filtry platí pro graf, produkty a seznam prodejů. Čísla nahoře mají pevná období a řídí se jen filtrem
   marketplace.
5. **Posledních 20 prodejů** (ve filtru): datum, produkt, marketplace, kusy, čistě v původní měně a v Kč.
   **Stav zdrojů:** u každého marketplace datum posledního prodeje v DB a kdy proběhla poslední úspěšná
   aktualizace: u Gumroadu a Cosmosu poslední úspěšné stažení denním agentem (jeho stav v
   `data/private/agent_state.json`), u Fabu a CGTraderu kdy naposledy přibyl záznam z ručního importu. Když je
   automatické stažení starší než 3 dny, zvýraznit (stejné pravidlo jako v e-mailu).

## Testy

- `overview.py` na vymyšlených datech: součty po obdobích, marketplace a produktech; vyloučené prodeje
  venku; vrácení; víc měn se nesčítá; chybějící kurz → Kč označené jako neúplné; nespárované produkty;
  hranice měsíce v místním čase (prodej 31. 1. 23:30 Praha patří do ledna).
- Načtení chybějících kurzů: každý den se stahuje jednou, pauza mezi requesty, výpadek ČNB nespadne.
- Stránka: spustí se bez chyby na demo datech. Pokud Streamlit má nástroj na testování stránky bez prohlížeče
  (myslím, že `AppTest`), ověřím v dokumentaci a použiju ho. Jinak ruční kontrola.
- `demo --dashboard` nesáhne na `data/private/`.

## Co M6 nedělá

- Žádné nasazení na internet, přihlašování ani sdílení. Jen lokálně.
- Žádné úpravy dat ze stránky (vyloučení prodeje dál příkazem `exclude`).
- Wishlisty a další zdroje nejsou součástí M6.

## Pořadí prací

1. `overview.py` + testy (výpočty).
2. Doplnění kurzů pro starší dny.
3. Stránka ve Streamlitu + příkaz `dashboard`.
4. `demo --dashboard`, screenshot do README, krátký odstavec v README.
5. Ověření na skutečných datech (Vítek otevře a porovná pár čísel s e-mailem).
