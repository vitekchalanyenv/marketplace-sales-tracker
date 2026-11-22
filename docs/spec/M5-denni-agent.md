# Specifikace M5: Denní agent

**Stav:** schváleno Vítkem 2026-11-22. Tentýž den změna z notifikace ve Windows na ranní e-mail, protože
notifikace nepřišla a Vítek chce souhrn každý den. Obsah souhrnu vybral Vítek, službu Resend navrhla AI
(Vítek chtěl službu s API zdarma).

## Cíl

Jednou denně se samo spustí stažení prodejů ze všech zdrojů a Vítkovi přijde **e-mail se souhrnem**,
**každý den, i když se nic neprodalo**. Souhrn je rozdělený do sekcí, aby šly později přidávat další
(wishlisty, sledování a podobně).

## Spouštění: Plánovač úloh Windows

- Úloha `marketplace-sales-tracker` **denně v 8:00**.
- **Počítač byl v 8:00 vypnutý:** úloha se spustí co nejdřív po zapnutí a přihlášení (`StartWhenAvailable`).
  Počítač se **nebudí**.
- Běží jen při přihlášeném Vítkovi, protože Chrome potřebuje jeho profil kvůli Cosmosu.
- Spouští se přímo `.venv\Scripts\pythonw.exe -m sales_tracker run daily` s pracovní složkou projektu,
  takže se neotevře okno konzole.
- Úlohu zaregistruje skript `scripts/install_task.ps1` a odebere `scripts/uninstall_task.ps1`.

**Zmeškané dny se dorovnají samy:** Gumroad bere posledních 30 dní a Cosmos stránkuje, dokud nenarazí na známé
transakce starší než 30 dní.

## Příkaz `run daily`

Postupně spustí kroky. **Každý krok běží samostatně**, takže chyba jednoho nezastaví ostatní.

1. `sync gumroad`
2. `sync cosmos` (headless, bez `--login`; přihlašuje se vždy Vítek sám)
3. `import fab`: soubory v `data/private/fab/` (idempotentní; když tam nic není, krok se přeskočí, nejde o chybu)
4. CGTrader a ruční kopie Cosmosu se doplní, až budou jejich importy hotové (M4b, M4a cesta 2).

Pak sestaví souhrn a pošle e-mail. `run daily --dry-run` souhrn jen vypíše a nic neodešle.

## Ranní souhrn (e-mail)

**Předmět:** `Prodeje 22. 11.: 1 nový prodej, čistě 12,34 USD`, nebo `Prodeje 22. 11.: bez nových prodejů`.
Když něco selhalo, předmět začíná `⚠ chyba: Cosmos ·`.

**Sekce:**

1. **Nové prodeje od minulého souhrnu:** každý prodej na vlastním řádku (marketplace, produkt, kusy, čistá částka,
   čas prodeje v místním čase). Když žádné nejsou, sekce to napíše.
2. **Refundy** (jen když nějaké jsou): marketplace, produkt, částka.
3. **Tento měsíc:** čistý příjem od začátku měsíce (Europe/Prague) po marketplacech a celkem, zvlášť pro každou
   měnu, bez převodu. Refundy se odečítají: u Fabu jako záporné řádky, u Gumroadu a Cosmosu se záznam se statusem
   refund nepočítá.
4. **Stav zdrojů:** u každého kroku `ok`, nebo `CHYBA` s krátkým důvodem. U Gumroadu a Cosmosu i čas posledního
   úspěšného stažení. Když stažení selže a poslední úspěch je 3 a víc dní starý, připíše se
   „naposledy staženo před N dny“. Při vypršeném přihlášení do Cosmosu je v souhrnu přímo příkaz
   `uv run python -m sales_tracker sync cosmos --login`.

**„Od minulého souhrnu“** znamená od posledního **úspěšně odeslaného** e-mailu, nikoli od posledního běhu. Do souhrnu
se tak dostanou i prodeje stažené mezitím ručně. Když e-mail neodejde, další souhrn je zopakuje. Stav se drží
v `data/private/agent_state.json` (nejvyšší `rowid` a seznam záznamů se statusem jiným než `sold` v době odeslání).
Při prvním běhu se jako výchozí bere stav databáze před stažením, takže e-mail nevypíše celou historii.

- E-mail obsahuje jen názvy produktů, počty a částky. Žádné tokeny ani údaje o zákaznících (zdroje je ani neukládají).
- E-mail má textovou i jednoduchou HTML verzi (nadpisy a odrážky).

## Odesílání: Resend

Ověřeno na dokumentaci 2026-11-22 (resend.com/pricing, docs/api-reference/emails/send-email, docs/api-reference/errors):
- Free: **100 e-mailů denně, 3 000 měsíčně**. Nám stačí 1 denně.
- `POST https://api.resend.com/emails`, hlavička `Authorization: Bearer <klíč>`, JSON `from`, `to`, `subject`,
  `text`, `html`. Úspěch vrací `{"id": …}`.
- Bez ověřené vlastní domény lze posílat **jen na e-mail majitele účtu** (chyba 403 „You can only send testing emails
  to your own email address“). To nám stačí, protože souhrn jde Vítkovi. Odesílatel je `onboarding@resend.dev`.
  Že tohle odesílání bez domény funguje, je **odvozené z chybové hlášky**. Ověří se prvním skutečným odesláním.
- Chyby: 401/403 (klíč, příjemce) a 429 (limit) se vypíšou s kódem a hláškou. Tvar těla chybové odpovědi
  dokumentace neukazuje, proto se z něj bere jen `message`, pokud tam je.
- `.env`: `RESEND_API_KEY`, `REPORT_EMAIL_TO` (Vítkův e-mail, ten z účtu Resend), volitelně `REPORT_EMAIL_FROM`.
  Klíč se nikdy nevypisuje.
- Když e-mail neodejde (chybí klíč, síť, limit), důvod se zapíše do logu, `run daily` skončí s kódem 1
  a další souhrn nové prodeje zopakuje.

## Log a stav

- `data/private/logs/daily_YYYY-MM-DD.log`: výstup všech kroků a celý souhrn (mimo git). Logy starší než 60 dní
  se mažou.
- `data/private/agent_state.json`: poslední úspěch každého automatického zdroje (Gumroad, Cosmos) a stav
  posledního odeslaného souhrnu.

## Testy (bez sítě a prohlížeče)

- Kroky podvržené funkcemi, odesílání jen zaznamenává e-maily:
  - e-mail přijde i bez prodejů,
  - nové prodeje jsou vypsané po kusech a sečtené v předmětu,
  - druhý souhrn je už nevypíše,
  - prodej stažený mimo `run daily` se dostane do dalšího souhrnu,
  - když odeslání selže, další souhrn prodeje zopakuje,
  - refund se vypíše v sekci Refundy,
  - součet za měsíc: Fab refund se odečte, refundovaný prodej z Cosmosu se nepočítá, minulý měsíc se nepočítá,
  - vypršené přihlášení do Cosmosu je v předmětu i ve stavu zdrojů s příkazem `--login`,
  - jeden krok spadne a ostatní doběhnou,
  - upozornění na stáří od 3 dnů,
  - `--dry-run` nic neodešle a nezmění stav.
- Odesílání přes Resend: přes podvržený HTTP transport se kontroluje URL, hlavička, JSON a chyby 401/403/429.
- Ostré odeslání a běh v Plánovači se ověřují ručně.

## Rozhodnutí Vítka (2026-11-22)

1. Počítač nebudit, úloha se spustí po zapnutí.
2. Upozornění na stáří stažení od 3 dnů.
3. **Souhrn e-mailem každé ráno v 8:00, i bez prodejů** (místo notifikace ve Windows). Obsah: nové prodeje
   po kusech, součty za aktuální měsíc a stav každého zdroje.
4. Služba s API zdarma, AI navrhla Resend.

## Mimo rozsah M5

- Týdenní shrnutí s komentářem a převod měn: samostatný milník.
- Wishlisty a další sekce: později, souhrn je na ně připravený.
- Běh na serveru nebo v cloudu: Cosmos potřebuje Vítkův profil v Chromu na tomhle počítači.
