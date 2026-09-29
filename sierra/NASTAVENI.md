# Přesné nastavení krok za krokem

Pořadí dodrž. Body 1–4 jsou povinné, bez nich studie buď nenaběhne, nebo bude počítat
jiná čísla než výzkum. Názvy položek v menu se můžou podle verze Sierry mírně lišit.

---

## 1. Globální nastavení Sierry

**Global Settings → General Settings → Time Zone**

| Položka | Hodnota |
|---|---|
| Time Zone | **New York (Eastern)** |

Inputy *RTH Start* a *RTH End* jsou v časové zóně grafu. Celý výzkum stojí na RTH 9:30–16:00
newyorského času. Když má graf jinou zónu, musíš o stejný posun upravit i tyto dva Inputy.

**Global Settings → Data/Trade Service Settings**

| Položka | Hodnota | Proč |
|---|---|---|
| Maximum Historical Intraday Days to Download → Non-Tick Data | **7000** | plná historie od 5/2008 |
| Intraday Data Storage Time Unit | 1 Second nebo 1 Minute | 1 Minute je menší a rychlejší |

**Cesta k datovým souborům** si opiš z *Global Settings → General Settings → Paths →
Data Files Folder*. Do ní patří `swing_presets.csv`.

---

## 2. Instalace studie

1. `Lukacino_MultiSwing.cpp` → `SierraChart\ACS_Source\` (při každé aktualizaci studie znovu)
2. `swing_presets.csv` → Data Files Folder z bodu 1
3. *Analysis → Build Custom Studies DLL* → vyber soubor → **Build**
4. V okně buildu musí být `The build is complete` bez chyb

---

## 3. Graf

*File → Find Symbol* → **ESZ26** (aktuální kontrakt) → otevři jako **Intraday Chart**.

**Chart → Chart Settings**

| Skupina | Položka | Hodnota | Proč |
|---|---|---|---|
| Bar Period | Type | Minutes | |
| Bar Period | Value | **1** | z denních barů nejde spočítat sigma VWAP pásem |
| Symbol | Continuous Futures Contract | **Date Rule Rollover – Back Adjusted** | bez toho zkreslí rollové skoky ATR i drawdown; samotné *Date Rule Rollover* nestačí, musí tam být i *Back Adjusted* |
| Data | Days to Load | **1000** pro živý provoz, **3300** pro Replay 2018–2026 | viz níže |
| Session Times | Use specific session times | **vypnuto** (celá Globex seance) | studie potřebuje i overnight |

**Ke Days to Load:** studie potřebuje nejdřív nasbírat historii, než dá první signál.
Konkrétně 210 seancí na klouzavé průměry a 252 seancí na drawdown od ročního maxima.
To je zhruba 14 měsíců. Při 1000 kalendářních dnech (asi 690 seancí) zbyde po zahřátí
ještě přes 400 seancí na signály. Míň než 600 kalendářních dnů nemá smysl.

---

## 4. Přidání studie

*Analysis → Studies → Add Custom Study → Lukacino Multi-Swing → Add → OK*

Hned po přidání otevři *Window → Message Log*. Musí tam být:

```
Multi-Swing: loaded 48 presets (48 valid) in 12 families from ...\swing_presets.csv.
```

| Co vidíš v logu | Co s tím |
|---|---|
| `48 presets (48 valid)` | v pořádku, pokračuj |
| `Preset file not found` | špatná cesta, zkontroluj Data Files Folder |
| `(44 valid)` a seznam chyb | pošli mi ty řádky, opravím parser |
| `apply to an INTRADAY chart` | graf není minutový |

---

## 5. Inputy

Otevři *Studies → Lukacino Multi-Swing → Settings*. Výchozí hodnoty jsou nastavené na
bezpečný provoz, takže **měnit musíš jen ty, které mají v posledním sloupci poznámku.**

### Global (0–9)

| # | Input | Výchozí | Změnit? |
|---|---|---|---|
| 0 | Trading Enabled | No | **zapni na Yes**, jinak se nic nepočítá |
| 1 | Mode | Signals only | nech, dokud nebude hotová order vrstva |
| 2 | Send Orders To Trade Service (LIVE!) | No | **nech No**, v tomto buildu stejně nic neposílá |
| 3 | Direction Filter | Long only | nech |
| 4 | Preset File | swing_presets.csv | jen když sis soubor přejmenoval |
| 5 | Reload Presets (toggle) | No | přepni tam a zpět po úpravě CSV |
| 6 | Risk Unit (contracts per preset) | 1.0 | 1 MES na preset, viz sizing níže |
| 7 | Instrument | MES | přepni na ES; přepočítává strop expozice (1 ES = 10 MES) |
| 8 | Entry Timing | Fill at RTH close | nech, odpovídá výzkumu |
| 9 | Journal CSV | swing_journal.csv | |

### Rodiny (10–33)

Dvanáct dvojic *Enabled* a *Weight*, všechny výchozí **Yes / 1.0**. Pořadí odpovídá síle
z výzkumu, první je nejsilnější:

| # | Rodina | alfa t |
|---|---|---|
| 10–11 | Limit RSI pullback | 3,03 |
| 12–13 | Close pod denním VWAP | 2,17 |
| 14–15 | Close pod týdenním VWAP | 2,12 |
| 16–17 | Reclaim krátké MA | 2,08 |
| 18–19 | Drawdown + RSI | 2,01 |
| 20–21 | IBS | 2,01 |
| 22–23 | Williams %R | 1,98 |
| 24–25 | VWAP pásmo | 1,88 |
| 26–27 | N-denní low | 1,78 |
| 28–29 | RSI oversold | 1,75 |
| 30–31 | Drawdown + IBS | 1,62 |
| 32–33 | Connors RSI | 1,61 |

Pro první testy nech všech dvanáct zapnutých. Vypínání jednotlivých rodin má smysl až
podle vlastních výsledků, ne podle dojmu.

### Risk (34–41)

| # | Input | Výchozí | Aktivní? | Poznámka |
|---|---|---|---|---|
| 34 | Max Gross Exposure (MES equivalents) | 60 | ano | ES se počítá jako 10 MES |
| 35 | Max Concurrent Presets | 48 | ano | 48 = neomezuje; snižování stojí hodně, viz níže |
| 36 | Max Presets Per Family | 4 | ano | rodina má právě 4 varianty, takže neomezuje |
| 37 | Max Presets Per Role | 12 | ano | největší role má 12 presetů, takže neomezuje |
| 38 | Daily Loss Limit USD | 0 | **ne, krok 3** | potřebuje order vrstvu |
| 39 | Max Drawdown Stop USD | 0 | **ne, krok 3** | |
| 40 | Scale In By Correction Depth | No | **ne, krok 3** | |
| 41 | Scale In Cap | 2.0 | **ne, krok 3** | |

**Výchozí capy schválně nic neořezávají**, aby kniha obchodovala přesně to, co bylo ověřeno.
Změřeno na 18 letech: snížení *Max Concurrent Presets* na 10 sníží počet obchodů z 6 222
na 3 514 a P&L ze 72 948 na 29 673 bodů. Cap totiž ubírá právě ty shluky vstupů v hlubokých
korekcích, kde je edge nejsilnější. Snižuj ho jen vědomě, jako rozhodnutí o riziku.

### Exekuce (42–47)

| # | Input | Výchozí | Aktivní? |
|---|---|---|---|
| 42 | Entry Type Override | As defined by preset | ano |
| 43 | Limit / Stop Offset (ticks) | 0 | ano |
| 44 | Entry Order Expiry (sessions) | 1 | ano |
| 45 | Max Slippage ticks | 8 | **ne, krok 3** |
| 46 | Flatten At Session End | No | **ne, krok 3** — a musí zůstat No, jsou to swingy |
| 47 | Time Stop Override (sessions) | 0 = použít preset | ano |

### TP / SL / RRR override (52–58)

**Tohle je odpověď na otázku, kde se nastavuje TP, SL a RRR.** Za normálních okolností nikde:
každý z 48 presetů si nese vlastní exit model, který pro něj byl ověřen. Osmnáct různých
exitů v CSV není nedodělek, je to výsledek testu — proto je override **výchozím stavem vypnutý**.

| # | Input | Výchozí |
|---|---|---|
| 52 | Exit Override (overrides ALL presets) | Use preset exits (validated) |
| 53 | Override SL (x ATR20) | 1.0 |
| 54 | Override RRR (TP = SL x RRR) | 2.0 |
| 55 | Override SL (ticks) | 80 |
| 56 | Override TP (ticks) | 160 |
| 57 | Override Breakeven (R, 0=off) | 0 |
| 58 | Override Trailing (x ATR20, 0=off) | 0 |

Input 52 má tři stavy:

- **Use preset exits** — každý preset jede svůj ověřený exit. Tohle chceš.
- **Override: ATR bracket** — na všech 48 presetů se vnutí SL = 53 × ATR20 a TP = SL × RRR (54).
- **Override: fixed ticks** — pevný SL (55) a TP (56) v ticích. Ticky jsou 0,25 bodu.

Breakeven (57) a trailing (58) platí jen když je override zapnutý.

**Co to stojí.** Změřeno na stejných datech, období 2016-06 až 2026-09:

| Nastavení | Obchodů | P&L | Průměrné držení | Win |
|---|---|---|---|---|
| Preset exity (výchozí) | 6 222 | 72 948 b. | 5,2 dne | 61 % |
| Override SL 1 ATR, RRR 2 | 7 594 | 58 390 b. | 4,0 dne | 52 % |
| Override SL 2 ATR, RRR 1 | 6 324 | 72 535 b. | 5,2 dne | 66 % |
| Time Stop Override 5 dní | 7 095 | 63 605 b. | 4,1 dne | 62 % |

Jednotný exit přes všech 48 presetů stojí 0–20 % P&L. Override je proto na experimenty,
ne na ostrý provoz. Když ho zapneš, výsledky z reportu už neplatí.

### Seance a diagnostika (48–51)

| # | Input | Výchozí | Poznámka |
|---|---|---|---|
| 48 | RTH Start | 09:30:00 | jen když má graf jinou časovou zónu |
| 49 | RTH End | 16:00:00 | jen když má graf jinou časovou zónu |
| 50 | Log Level | Info | |
| 51 | Draw Signals On Chart | Yes | |

---

## 6. Sizing

48 presetů má dohromady průměrnou expozici 9,5 ES ekvivalentu, ve špičce zhruba 4–5× tolik.

| Co chceš | Instrument | Risk Unit | Max Gross | Průměrná expozice |
|---|---|---|---|---|
| Doporučeno | MES | 1.0 | 60 | 0,95 ES, špička 4,8 ES |
| Poloviční riziko | MES | 0.5 | 30 | 0,48 ES |
| Velké kontrakty | ES | 1.0 | 6 | 9,5 ES, pro většinu účtů moc |

---

## 7. Kontrola, že to počítá správně

Po přidání studie a nastavení *Trading Enabled = Yes*:

1. **Graf:** modrá čára je týdenní VWAP, oranžová měsíční. Musí kopírovat cenu, ne být rovné.
2. **Zelené šipky** pod bary označují dny, kdy nějaký preset vstoupil.
3. **Message Log** vypíše řádek se stavem při každé změně počtu otevřených pozic.
4. **Data Files Folder** obsahuje `swing_journal.csv` se sloupci
   `preset_id, family, signal_day, entry_day, exit_day, side, entry, exit, pnl_pts, mae, mfe, bars, reason`.

Ledger se při každém plném přepočtu grafu **přepíše od začátku**, ne dopisuje. Je to tak
schválně, jinak by se ti při každém reloadu grafu zdvojily obchody.

---

## 8. Replay test pro paritu

Replay pouštěj opakovaně, je to hlavní průběžný test. Jedno kolo trvá při rychlosti
*Maximum* řádově desítky minut, podle stroje.

### Jednorázová příprava

1. *Chart Settings → Days to Load* = **3300** (pokryje 2018–2026)
2. Počkej, až se data stáhnou. Sleduj *Window → Message Log*, dokud neskončí stahování.
3. *Trading Enabled* = **Yes**, *Mode* = **Signals only**, *Send Orders To Trade Service* = **No**.
   Replay tak nikdy nesáhne na účet.

### Jedno kolo replaye

1. V Data Files Folder **smaž nebo přejmenuj** `swing_journal.csv`.
   Studie si ho sice při plném přepočtu přepisuje od začátku, ale replay běží po barech,
   ne jedním přepočtem, takže čistý start je jistota.
2. *Chart → Replay Chart*
   - Start Date **2018-01-01**
   - Replay Speed **Maximum**
   - Replay Mode **Standard**
   - *Clear chart before replay* zapnuto
3. Nech doběhnout až do konce. Během běhu se v Message Logu objevuje řádek při každé
   změně počtu otevřených pozic — když je log němý celé měsíce, něco je špatně
   (většinou *Trading Enabled = No* nebo málo načtených dní).
4. Po doběhnutí zkontroluj `swing_journal.csv`: první obchody mají být z **jara 2019**
   (2018 padne na zahřívání indikátorů), poslední z konce replaye, a mají tam být
   všechny **rodiny (12)** i **presety (48)**. Za období 2019-03 až 2026-09 dává offline
   harness **4 701 obchodů a 67 320 bodů** — replay by měl být v řádu stejný. Pár set
   řádků znamená, že replay nedojel nebo se kniha nezahřála.
5. Porovnej ho skriptem — přímo na tom stroji, kde běží Sierra:

   ```
   python sierra\check_replay.py cesta\k\swing_journal.csv
   ```

   Vypíše rozdíl preset po presetu, běží asi sekundu. Potřebuje **jen Python**, nic se
   neinstaluje — žádné balíčky, žádný kompilátor, žádná tržní data. Referenční ledger je
   v repu jako `sierra/reference_journal.csv`. Kdyby to nešlo, pošli mi `swing_journal.csv`
   a proženu ho tady.

   `--rebuild` referenční ledger přegeneruje z aktuálního zdroje studie. To má smysl jen
   tady, kde jsou data — po každé úpravě `Lukacino_MultiSwing.cpp` je potřeba ho obnovit,
   jinak bys replay porovnával proti staré verzi.

### Co replay ověřuje a co ne

Offline harness (`sierra/run_parity.py`) už teď projíždí stejnou C++ logiku proti Pythonu
na 4 122 506 barech a sedí: **32 ze 48 presetů má identickou množinu vstupů**, 39 ze 48 má
překryv vstupů ≥ 97 %, 6 185 obchodů v Pythonu proti 6 222 ve studii a P&L 77 329 proti
72 948 bodům, tedy **94,3 % Pythonu**. Ten rozdíl je schválně: když stop i target padnou
do jedné seance, studie je na denním rozsahu vyhodnotí **stopem napřed**, zatímco výzkum
prochází 30minutové bary. Živé P&L pod backtestem je správný směr.

Replay ověřuje to, co offline test ověřit nemůže — chování samotné Sierry: hranice seancí,
rollover kontraktu, pořadí barů a to, že studie počítá stejně, když data přicházejí po jednom
baru, a ne najednou.

Proto se replay porovnává **proti offline harnessu, ne proti Pythonu**. Obojí je tentýž C++ kód
nad týmž instrumentem, takže se mají shodovat na kus. Každý rozdíl je tím pádem záležitost
Sierry, ne logiky — a `check_replay.py` ti ho ukáže preset po presetu.

### Když se čísla rozejdou

Nejčastější příčiny, v pořadí podle pravděpodobnosti:

| Příčina | Jak se pozná |
|---|---|
| Graf není *Back Adjusted* | rozjedou se hlavně dlouhé obchody přes rollover |
| Graf není v zóně New York | posunou se vstupy o celé seance |
| *Use specific session times* je zapnuté | chybí overnight, rozjede se VWAP i IBS |
| *Days to Load* je malé | chybí začátek, kniha se nestihla zahřát |

Když sedí všechno tohle a rozdíl zůstává, pošli mi `swing_journal.csv` a k němu výpis
Message Logu. Rozdíl mezi replayem a offline harnessem není nikdy "šum" — offline je
deterministický a proti Pythonu sedí.

## Časté chyby

| Příznak | Příčina |
|---|---|
| Žádné signály, log je v pořádku | *Trading Enabled* je na No, nebo je načteno málo dní |
| VWAP čáry jsou na nule | graf nemá objemy, nebo je to non-intraday graf |
| Signály na jiných dnech než v backtestu | graf není *Back Adjusted*, nebo je jiná časová zóna |
| Replay dá zhruba dvojnásobek obchodů od data startu | studie z verze před opravou live guardu — přebuildi DLL |
| Ledger má dvakrát tytéž obchody | starý soubor z verze před touto opravou, smaž ho |
| `check_replay.py` hlásí 0/48 shodných vstupů | ledger je ze staré verze studie, která psala datum v zobrazovacím formátu Sierry — přebuildi DLL |
