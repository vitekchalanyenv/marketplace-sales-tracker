# Specifikace M5c: připomínka ručních zdrojů a měsíční shrnutí v ranním e-mailu

**Stav:** schváleno Vítkem 2026-11-23 (varování Fab 7 dní, CGTrader po 10. dni; měsíc jen čísla, bez Claude).
Napsáno, testy prošly; na skutečných datech ověřeno, že stav Fab/CGTrader i měsíční sekce za říjen odpovídají
(čísla shodná s přehledem). Ostrý e-mail s měsíční sekcí přijde 1. 12.

## 1. Připomínka ručních zdrojů (Fab, CGTrader)

Problém: Gumroad a Cosmos stahuje agent sám a e-mail hlídá jejich stáří. Fab a CGTrader se nahrávají ručně a když
report zapomeneš stáhnout, e-mail hlásí „ok“ a data tiše chybí.

**Do kdy máme data:**
- **Fab:** konec období z názvu souboru reportu (`<od>_<do>_fab_daily_sales_report.csv`, formát ověřen v M3), nejpozdější
  ze všech souborů v `data/private/fab/`. Když název tomuhle tvaru neodpovídá, použije se nejnovější prodej z Fabu
  v databázi a u řádku bude „(podle posledního prodeje)“.
- **CGTrader:** report je vždy za jeden měsíc. Platí měsíc nejnovějšího prodeje v reportech v `data/private/cgtrader/`
  (report bez prodejů měsíc neprozradí). Report stažení („Item downloads“) se nepočítá.

**V sekci „Stav zdrojů“:**
- `Fab: ok – data do 23. 11.` (jen datum, ne den v týdnu ani čas).
- Když je to **7 dní a víc** (od konce období reportu do dneška): `Fab: ⚠ data jen do 10. 11. (13 dní), stáhni nový report`.
  Varování je i v předmětu: `⚠ starý report: Fab`.
- `CGTrader: ok – reporty do října 2026`. Varování po **10. dni měsíce**, když chybí report za minulý měsíc:
  `CGTrader: ⚠ chybí report za listopad 2026`. Report bez prodejů v daném měsíci nejde odlišit od chybějícího,
  takže když v měsíci nic neprodáš, varování přijde taky. Proto jen v sekci, ne v předmětu. Až bude CGTrader API,
  tohle zmizí.

## 2. Měsíční shrnutí

**Kdy:** první ranní e-mail v měsíci (stejně jako týdenní: odeslání se pamatuje v `agent_state.json`, takže když je
PC 1. vypnuté, přijde druhý den). Předmět dostane `· měsíční shrnutí`. Když vyjde 1. na pondělí, jsou v e-mailu obě
sekce, měsíční nahoře.

**Sekce „Minulý měsíc (říjen 2026)“, čísla počítá kód** (stejné výpočty jako přehled `overview.py`):
- `Celkem: 12 ks, čistě 150,00 USD (≈ 3 300 Kč)` (vymyšlená čísla),
- po marketplacech (seřazeno podle příjmu): `Cosmos: 8 ks, čistě … (≈ … Kč)`,
- nejlepší produkt podle příjmu v Kč, s kusy,
- srovnání s předchozím měsícem: `Září 2026: 6 ks, ≈ 1 650 Kč (změna +100 %)`,
- `Letos celkem: …` (od 1. 1. do konce minulého měsíce; v lednu za celý minulý rok s nadpisem „Rok 2026“).
- Pravidla jako všude: bez vyloučených prodejů, Kč kurzem ČNB ke dni prodeje, měny se nesčítají, chybějící kurz
  → „Kč nedostupné“.

**Bez komentáře Claude** (rozhodnutí Vítka): týdenní komentář už je, měsíc jsou jen čísla.

## Testy

- Fab: datum z názvu souboru, nejpozdější ze souborů, název mimo formát → poslední prodej, varování od 7 dní,
  v předmětu.
- CGTrader: měsíc z reportů, report stažení se nepočítá, varování po 10. dni, bez varování do 10.
- Měsíc: sekce jen v prvním e-mailu měsíce, po zmeškaném 1. přijde 2., neopakuje se, při neodeslaném e-mailu se
  zopakuje; čísla na vymyšlených datech včetně refundu, vyloučeného prodeje, víc měn, změny proti měsíci
  předtím a ledna (rok předtím).
- Demo: „dnes“ v demu je pondělí 26. 1., takže měsíční sekce se v demu neukáže. Test ji zkusí zvlášť s jiným datem.

## Rozhodnutí Vítka (2026-11-23)

1. Fab varuje po 7 dnech, CGTrader po 10. dni měsíce.
2. Měsíční shrnutí jen s čísly od kódu.
