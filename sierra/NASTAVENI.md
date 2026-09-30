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

### Aktualizace studie: studii do grafu znovu nepřidáváš

Po buildu Sierra DLL sama vymění za běhu. V Message Logu to vypadá takhle:

```
Unloaded DLL: C:\SierraChart\Data\Lukacino_MultiSwing.dll
Loading DLL:  C:\SierraChart\Data\Lukacino_MultiSwing.dll
Multi-Swing 2026-09-30.10: loaded 48 presets (48 valid) in 12 families
```

Studie zůstane na grafu, **nastavení Inputů si podrží** — nové Inputy se přidávají jen na konec a
existující se nikdy nepřečíslovávají, takže reload nikdy nic nepřepíše. Přidávat studii znovu
nebo přenastavovat Inputy není potřeba.

**Zkontroluj ale, že se build opravdu povedl** — podle čísla verze, ne podle ničeho jiného.
Sierra kompiluje na vzdáleném serveru (`build.sierrachart.com`) a stará DLL umí zůstat nahraná,
přičemž `Unloaded DLL` / `Loading DLL` v logu vypadá naprosto stejně jako úspěšná výměna.

Hláška **`The compiler response is empty.` nic neznamená** — objevuje se i u buildů, které
proběhnou správně. Změřeno na dvou po sobě jdoucích buildech: oba ji měly, první nahrál starou
DLL (bez verze), druhý novou (`Multi-Swing 2026-09-30.10:`). Jediné spolehlivé je to číslo.

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
| 1 | Mode | Signals only | pro obchodování na Simu přepni na **Full auto**, viz kapitola 9 |
| 2 | Send Orders To Trade Service | No | rozhoduje mezi **grafovou simulací** (No) a **účtem** (Yes), viz kapitola 9 |
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
| 38 | Daily Loss Limit USD | 0 | **ano** | 0 = vypnuto; po ztrátové seanci nad limit stojí kniha jednu seanci |
| 39 | Max Drawdown Stop USD | 0 | **ano** | 0 = vypnuto; propad od vrcholu nad limit zastaví vstupy až do reloadu |
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

### Limity ztrát (38, 39)

Počítají se z **vlastního ledgeru studie**, ne z účtu — je to tentýž P&L, který se zapisuje
do `swing_journal.csv`, takže limity kousnou přesně do toho, co kniha udělala, v Replayi
i na Simu stejně. Přepočet na dolary: MES 5 USD za bod, ES 50, krát *Risk Unit*.

Obě zastaví jen **nové vstupy**. Otevřené pozice si nechají svůj stop a target a dojedou
do konce — to je schválně. Jsou to swingy držené přes noc a nucený výstup v momentě, kdy
limit sepne, realizuje tu nejhorší cenu pohybu.

- **38 Daily Loss Limit** — kniha rozhoduje jednou za seanci, na close, takže všechny vstupy
  i výstupy jednoho dne padnou ve stejný okamžik. Limit, který by zastavil obchodování „do
  konce dne", by neměl co zastavit. Co udělat může, je postavit knihu na **jednu následující
  seanci**, a to dělá.
- **39 Max Drawdown Stop** — propad realizovaného P&L od jeho vrcholu. Sepne natrvalo,
  dokud studii nereloaduješ.

Co to stojí, změřeno na 2015–2026 (48 presetů, MES, Risk Unit 1):

| Nastavení | Obchodů | P&L | Kolikrát sepnul |
|---|---:|---:|---:|
| vypnuto | 6 637 | 73 729 b. | — |
| Daily Loss 5 000 USD | 6 330 | 67 846 b. | 22× |
| Daily Loss 1 000 USD | 5 917 | 57 659 b. | 171× |
| Max Drawdown 20 000 USD | 1 289 | 6 282 b. | 1× |

**Je to pojistka, ne vylepšení.** Každá úroveň stojí P&L. Nastav ji podle toho, kolik jsi
ochoten ztratit, ne podle toho, kde vychází nejlíp.

### Per-rodinový override TP/SL (65–88)

Dvanáct dvojic, v pořadí rodin z Inputů 10–33:

| # | Input | Výchozí |
|---|---|---|
| 65, 67, … 87 | Fam*k* Override SL (x ATR20, 0 = preset) | 0 |
| 66, 68, … 88 | Fam*k* Override RRR (0 = preset) | 0 |

**Nula znamená „nesahej"**, takže ve výchozím stavu kniha obchoduje přesně ty exity, které
byly pro každý preset ověřené. Ověřeno regresí na 4 122 506 barech: s výchozími hodnotami je
ledger **bit-identický** s verzí před přidáním těchto Inputů.

Když vyplníš jen SL, target si podrží vlastní RRR presetu — což je obvykle to, co chceš,
když stop rozšiřuješ. Globální override (Input 52) má přednost: říká „ALL presets" a myslí to
vážně. Změřeno, rodina 6 (IBS) ze SL presetu na 2 ATR: 941 → 788 obchodů a 8 024 → 5 393 bodů,
a **žádná jiná rodina se nehnula**.

Per preset to přes Inputy nejde a nepůjde — 48 × 2 by se do limitu 128 nevešlo. Na to je
sloupec `exit` v `swing_presets.csv`.

### Seance a diagnostika (48–51)

| # | Input | Výchozí | Poznámka |
|---|---|---|---|
| 48 | RTH Start | 09:30:00 | jen když má graf jinou časovou zónu |
| 49 | RTH End | 16:00:00 | jen když má graf jinou časovou zónu |
| 50 | Log Level | Info | |
| 51 | Draw Signals On Chart | Yes | zelené šipky pod bary |

### Diagnostika (64)

| # | Input | Výchozí | Co dělá |
|---|---|---|---|
| 64 | Feature Dump CSV (blank = off) | prázdné | vypíše každý den všechny hodnoty, ze kterých vstupní pravidla počítají |

Nech prázdné, dokud tě o to nepožádám. Když tam dáš třeba `swing_features.csv`, studie
vedle ledgeru zapisuje řádek na každou uzavřenou seanci: OHLC, **objem**, ATR20, všechny tři
VWAP kotvy i jejich sigma, RSI2, IBS, ConnorsRSI, Williams %R, drawdown a klouzavé průměry.

Je to na ladění parity. Ledger říká, **které dny** se obchodovalo; tenhle soubor říká, **z čeho**
se ta rozhodnutí počítala, takže jde rozlišit chybu ve studii od rozdílu v datech. Porovnává
se skriptem `sierra/check_features.py` (ten běží jen tady, potřebuje výzkumná data).

### Zobrazení na grafu (59–63)

| # | Input | Výchozí | Co dělá |
|---|---|---|---|
| 59 | Show Status Box On Chart | **Yes** | rámeček se stavem, viz níže |
| 60 | Status Box Corner | Top left | roh grafu |
| 61 | Status Box Font Size | 10 | |
| 62 | Label Signals With Preset Count | No | k šipce dopíše `3x` = kolik presetů ten den vstoupilo |
| 63 | Label Only The Last N Sessions | 60 | 0 = všechny; při replayi nech omezené |

Status box vypadá takhle:

```
LUKACINO MULTI-SWING
mode      FULL AUTO - ORDERS LIVE
presets   48 in 12 families
open      7 presets
book      9 contracts   position 9
days      2431   risk unit 1.00 MES
```

Barva rámečku říká, v čem jsi, aniž bys musel číst:

| Barva | Stav |
|---|---|
| **červená** | Full auto a *Send Orders* = Yes — příkazy odcházejí na účet |
| zelená | signály, semi, nebo Full auto v grafové simulaci — žádný účet |
| žlutá | `STOPPED` (odmítnuté příkazy) nebo `HALTED` (limit ztráty) — nové vstupy neodcházejí |
| šedá | *Trading Enabled* = No, studie nepočítá |

Pozor na zelenou u *Full auto*: znamená „žádný účet", ne „nic se nedělá". V grafové simulaci
příkazy odcházejí a plní se, jen se jich nedotkne účet — řádek `mode` to řekne přesně
(`FULL AUTO - chart simulation only`).

Řádek `book ... position ...` je nejdůležitější: první číslo je, kolik kontraktů kniha chce
držet, druhé kolik jich na účtu skutečně je. Když se ta dvě čísla rozejdou a nedorovnají,
někde se odmítl příkaz — podívej se do Message Logu.

**K popiskům (62):** při plném replayi je nech vypnuté nebo omezené. Kreslí se jako chart
drawings a několik tisíc jich graf zpomalí. Vykreslují se odzadu od posledního baru, takže
`60` znamená šedesát nejnovějších signálních dnů. Když je vypneš, studie po sobě ty svoje
popisky smaže.

---

## 6. Sizing

48 presetů drží v průměru 12 pozic současně, ve špičce až všech 48.

**Max Gross Exposure (Input 34) se počítá v MES ekvivalentech.** Jeden otevřený preset stojí
*Risk Unit* × 1 na MES, ale *Risk Unit* × **10** na ES. Když dáš cap pod tuhle hodnotu, odmítne
se **první vstup každé seance navždy** a kniha zůstane prázdná — a v grafu to vypadá úplně
stejně jako klidný trh. Proto to studie od verze `2026-09-30.11` hlásí sama:

```
BLOCKED    Max Gross 6 < one preset (10) - no preset can ever enter
```

| Co chceš | Instrument | Risk Unit | Max Gross | Kolik je reálně v trhu |
|---|---|---|---|---|
| Doporučeno | MES | 1.0 | **60** | průměr 12 MES = 1,2 ES, špička 4,8 ES |
| Poloviční riziko | MES | 0.5 | **30** | průměr 0,6 ES |
| Velké kontrakty | ES | 1.0 | **600** | průměr **12 ES**, špička 48 ES — pro většinu účtů moc |

Změřeno na 4 122 506 barech: `ES / 1.0 / cap 600` i `MES / 1.0 / cap 60` dají celou knihu
6 637 obchodů, **`ES / 1.0 / cap 6` dá nulu.**

Max Gross zároveň nastavuje `sc.MaximumPositionAllowed`, Sierřin vlastní tvrdý strop na
pozici. Ten se ale počítá v kontraktech obchodovaného instrumentu, ne v MES ekvivalentech,
takže se převádí (`Max Gross ÷ 10` na ES, `÷ 1` na MES). Do verze `2026-09-30.13` se tam
posílalo nepřevedené číslo a na ES byl ten záchytný strop 10× volnější než strop knihy.
Ověřeno v offline simulaci příkazů: `ES / cap 600` a `MES / cap 60` teď dávají **identických
9 821 vstupů a špičku pozice 60**; předtím se lišily.

Cap 60 na ES **není stejné riziko jako 60 na MES** — pustí jen 6 otevřených presetů, což knihu
ořeže stejně tvrdě jako *Max Concurrent Presets* 6 a výsledky z reportu tím přestanou platit.

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

**Změřeno 29. 9. 2026:** replay s *Days to Load* 400 a startem 2018-01-01 natáhl historii
od 2016-08-15 a na okně 2016-10 až 2019-11 dal **1 726 obchodů a 7 530 bodů proti 1 726 a
7 530 bodům** offline, tedy 48 ze 48 presetů s identickou množinou vstupů. Rozdíl byl jen
v prvních devíti seancích grafu, kde se indikátory ještě nezahřály. Sierra si tedy nic
nepřidává — viz `sierra/README.md`, sekce *Výsledek Replay*.

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
3. Nech běžet. V Message Logu naskakuje řádek při každé změně počtu otevřených pozic —
   když je log němý celé měsíce, něco je špatně (většinou *Trading Enabled = No* nebo
   málo načtených dní).

   **Nemusíš dojet až do konce.** Replay klidně zastav dřív; skript porovná jen tu část,
   kterou pokrývá, a posledních 30 dní zahodí — pozice otevřené v momentě zastavení se
   do ledgeru nedostanou a jinak by vypadaly jako rozdíl. Na první kontrolu stačí rok
   dva za zahřívací fází.
4. Po doběhnutí zkontroluj `swing_journal.csv`: první obchody jsou z prvních seancí, které
   graf natáhl (zahřívací fáze — skript je sám zahodí), poslední z konce replaye, a mají tam být
   všechny **rodiny (12)** i **presety (48)**. Za období 2019-03 až 2026-09 dává offline
   harness **4 701 obchodů a 67 320 bodů** — replay by měl být v řádu stejný. Pár set
   řádků znamená, že replay nedojel nebo se kniha nezahřála.
5. Porovnej ho skriptem — přímo na tom stroji, kde běží Sierra:

   ```
   python sierra\check_replay.py cesta\k\swing_journal.csv
   ```

   Pouští se ve **Windows Command Prompt nebo PowerShell**, ne v Sierře, ze složky repa,
   ve které je podsložka `sierra`. Vypíše rozdíl preset po presetu, běží asi sekundu.
   Potřebuje **jen Python**, nic se neinstaluje — žádné balíčky, žádný kompilátor, žádná
   tržní data. Referenční ledger je v repu jako `sierra/reference_journal.csv`. Kdyby to
   nešlo, pošli mi `swing_journal.csv` a proženu ho tady.

   Skript sám zahodí **prvních 60 dní** replaye jako zahřívací fázi a napíše, kolik obchodů
   tím nesrovnával — replay začíná se studenými indikátory, zatímco referenční ledger je
   natažený od 2015 a je teplý od prvního řádku. Počítat ten rozdíl jako chybu Sierry by
   skutečnou chybu schovalo do šumu. `--warmup 0` porovná i je, `--warmup 90` zahodí víc.

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

## 9. Obchodování na Sim účtu (replay i živě)

Studie umí posílat příkazy. Na jednom grafu je ale **jedna pozice**, ne 48. Studie proto drží
pozici rovnou tomu, co kniha chce držet, a **ke každému otevřenému presetu pracuje jeho vlastní
stop a target** jako samostatný příkaz na jeho velikost. Velikost na preset je *Risk Unit* ×
váha rodiny, tedy přesně to, na čem ledger počítá P&L.

**Proč ne prosté dorovnávání.** První verze posílala jeden čistý market příkaz denně. Změřeno
(`sierra/check_netting.py`): **39 % výstupů knihy padne na stop, target nebo trail**, tedy na
cenu, která není close — a čisté dorovnání je všechny zahodí, protože preset, který vypadl
stopem, a jiný, který týž den vstoupil, se vykrátí. Účet by pak obchodoval **knihu bez stopek**,
ne tu ověřenou. Na letech 2016–2026 by to vydělalo o 15 % víc, ale nejhorší den je o 48 % horší
(−3 848 vs −2 603 bodů). Není to bonus, je to jiná strategie.

Vyplněný stop sníží pozici okamžitě, zatímco kniha ten preset uzavře až na konci seance. Studie
si to pamatuje, takže mezitím pozici nedokoupí zpátky — jinak by se z každé stopky stal
round trip za horší cenu.

### Rychlost replaye ve Full auto

V *Signals only* a *Semi-auto* je rychlost jedno — nic se neposílá. Ve Full auto na ní **od verze
`.17` prakticky nezáleží**, a stojí za to vědět proč, protože předtím na ní záleželo hodně.

Preset, který kniha zavřela, odchází **svým vlastním bracketem**: jeho target (sell limit nad trhem)
se posune tick pod trh a vyplní se; preset bez targetu má posunutou stopku tick nad trh, kde se
spustí okamžitě. Ten příkaz je normální pracující příkaz — studie si ho pamatuje, nechá ho běžet,
a když trh odejde jinam, posune ho za ním. Kontrakty se pustí ze evidence teprve ve chvíli, kdy
Sierra ohlásí, že bracket už žádné živé děti nemá. Do té doby se počítají jako držené, takže se
nikdy nenabídnou tržnímu prodeji — a to byl přesně ten refusal, co ti dvakrát zamkl objednávkovou
vrstvu.

Tržní prodej zůstal jen pro kontrakty, které **nehlásí žádný preset**: co po sobě nechal zrušený
bracket a co studie na účtu najde a nedokáže nikomu přiřadit. Ty krycí příkaz nemají, takže je
Sierra přijme. Posílají se jednou a pak se osm volání nic dalšího nenabízí, aby se ten samý
kontrakt neprodal dvakrát, než se fil ohlásí.

Změřeno offline na 4 680 seancích (ES, risk unit 1), kde se fil záměrně zdržuje o daný počet volání
studie — sloupec „odmítnuto jako kryté" je ten stav, co končil `STOPPED`:

| zdržení filu | vstupů (`.16`) | vstupů (`.17`) | odmítnuto jako kryté (`.16` → `.17`) | přeprodejů (`.17`) |
|---|---|---|---|---|
| 0 volání | 9 332 | 9 367 | 5 → **0** | **0** |
| 1 volání | 46 | 9 367 | 5 → **0** | **0** |
| 2 volání | 46 | 9 367 | 5 → **0** | **0** |
| 5 volání | 142 | 9 367 | 19 → **0** | **0** |
| 10 volání | 73 | 9 367 | 8 → **0** | 117 |

Ve `.16` se to při jakémkoli zdržení složilo — z 9 332 vstupů zbylo 46. Ve `.17` je to na zdržení
filu **nezávislé** až k sedmi voláním studie; teprve za tou hranicí se začne nabízet kontrakt,
který je ještě na cestě z účtu.

Prakticky:

- **Full auto replay můžeš pustit rychle.** `10×` je pořád rozumné číslo, ale `7680×` už samo o sobě
  není důvod, proč by se příkazy odmítaly.
- **Dlouhé běhy (2008–2026) jeď stejně v *Semi-auto*.** Žurnál je to, co se porovnává, parita
  99,7 % se měřila takhle, a Full auto nemá nad osmnácti lety co dokázat navíc.
- Full auto si nech na **pár měsíců**, na ověření, že příkazy a brackety opravdu chodí na graf.
- Co ve Full auto sleduj místo rychlosti: `position` ve status boxu trvale **nad** `book`. Znamená
  to, že něco na účtu drží a nikdo se k tomu nehlásí; v logu k tomu bude řádek
  `CANNOT CLOSE <preset>` nebo `EXIT ... did not fill in 8 calls`.

Co v logu uvidíš nově:

| řádek | znamená |
|---|---|
| `EXIT <preset> through its own bracket - target order N moved to X` | normální odchod presetu, přes jeho vlastní target |
| `EXIT <preset> through its own bracket - stop order N moved to X` | totéž u presetu, co nemá target (signální výstup) |
| `EXIT <preset> still working - the market left it behind` | trh odešel od posunutého příkazu, studie ho posouvá za ním (jen při `Log Level = Debug`) |
| `EXIT <preset> did not fill in 8 calls` | příkaz se nevyplnil, bracket se zrušil, kontrakty jdou na trh |
| `SELL N - N contract(s) on the account that no preset claims` | úklid kontraktů bez vlastníka; **N by mělo být malé** |
| `CANNOT CLOSE <preset>` | ty kontrakty studie zavřít neumí — zavři je ručně v *Trade > Trade Orders and Positions* |

### Tři režimy, ne dva

Input 2 *Send Orders To Trade Service* není „posílat / neposílat". Rozhoduje, **kam** příkazy
jdou, a obě polohy jsou plnohodnotný běh:

| Input 2 | Kam příkazy jdou | Vidět na grafu | Vidět v *Trade Orders and Positions* | Potřebuje účet |
|---|---|---|---|---|
| **No** | do **vlastní simulace grafu** — plní se proti barům grafu | **ano** | ne | **ne** |
| **Yes** | do trade service (Sim nebo ostrý účet podle menu *Trade*) | ano | ano | ano |

**Pro Full auto to volba není: musí být Yes.** V `No` jde vše do vlastní simulace grafu, a ta
**odmítá `ModifyOrder` i `CancelOrder`** — potvrzeno z jeho logu: s `Yes` projde
`EXIT ... through its own bracket - target order 162534 moved to 7729.50`, s `No` přijde na tentýž
příkaz `could not steer ... Sierra returned -1`. Vstupy se přijímají v obou režimech, což je
přesně to, co dělá `No` zrádným: pozice roste a nejde ji sundat ničím jiným než tím, že Sierra sama
vyplní stopku nebo target. Od `.19` to studie napíše do logu a dá do status boxu
`FULL AUTO - no exits: set Input 3 to Yes`.

`No` je tedy pro *Signals only* a *Semi-auto*, kde se neposílá nic.

`No` **není paper mód**. Příkazy se opravdu zadávají, opravdu se plní, pozice se kreslí na graf
a `sc.GetTradePosition` ji hlásí, takže i status box ukazuje `position`. Jen se jí nedotkne
žádný účet. Pro test replaye je to **ten správný režim**: fily jsou deterministické z barů
grafu, není co špatně nastavit a k brokerovi nemůže nic uniknout.

### Zapnutí pro účet (Input 2 = Yes)

Input 2 = Yes je **nutná, ale nestačí**. Sierra brání příkazům ze studií ještě podruhé, na
úrovni menu Trade, a ani jeden z těch přepínačů není z dialogu studie vidět. Každý z nich
odmítá stejným generickým `-1`.

| Kde | Co |
|---|---|
| *Trade → Trade Simulation Mode On* | **zapnout první** — tohle rozhoduje simulace vs. ostrý účet, ne studie |
| *Trade → Auto Trading Enabled - Global* | zaškrtnout |
| *Trade → Auto Trading Enabled for Chart* | zaškrtnout **pro tenhle graf** (globální ho nenahradí) |
| Graf → *Trade Window*, nebo *Chart Settings → Trading* | vybrat Sim účet |
| Input 0 *Trading Enabled* | Yes |
| Input 1 *Mode* | **Full auto** |
| Input 2 *Send Orders To Trade Service* | **Yes** |

Pořadí dodrž: Trade Simulation Mode **nejdřív**. Input 2 sám o sobě neříká „simulace" —
říká „posílej", a kam to jde, určuje menu Trade.

#### Auto Trading for Chart zaškrtni jako POSLEDNÍ, až replay běží

Tohle stálo hodinu hledání, tak natvrdo: *Trade → Auto Trading Enabled for Chart* si Sierra
**sama shazuje**, kdykoli se graf přenačte, změní symbol, nebo **když se spustí chart replay**.
Zaškrtnutí před startem replaye je tedy k ničemu — start ho zhasne a každý `sc.BuyEntry` pak
vrací `-1`.

Správné pořadí pro full auto replay:

1. Spusť replay
2. **Teprve teď** zaškrtni *Trade → Auto Trading Enabled for Chart*
3. Zkontroluj *Trade → Auto Trading Enabled - Global*
4. Přepni Input 5 *Reload Presets* na opačnou hodnotu (zvedne případnou západku `STOPPED`)

**Jak `-1` z téhle brány poznáš:** Sierra u něj do Message Logu nenapíše **nic**. Odmítá volání
ještě předtím, než z něj vznikne příkaz, takže v logu jsou jen řádky studie a žádný Sierry
vlastní. Když Sierra příkaz naopak postaví a pak ho odmítne (cena, limit, účet), řádek o tom
napíše. Mlčící `-1` = tahle brána nebo chybějící trade account, nic jiného.

Rozhodující test, když si nejsi jistý: nech replay běžet a pošli **ručně z Trade Window** jeden
market BUY s bracketem. Projde-li, brána je otevřená a problém je jinde. Neprojde-li, je to
nastavení a skript s tím nemá nic společného.

#### Continuous back-adjusted graf ([CB]) je pro full auto v pořádku

Na `ESZ26_FUT_CME [CB]` ukazuje graf pro rok 2019 ES kolem 3630, i když reálně bylo ~2900 —
data jsou posunutá o rolovací offset. Nabízí se otázka, jestli trade service neodmítne stop a
target, které studie počítá z grafu, protože reálný kontrakt je na úplně jiné úrovni.

**Neodmítne.** Ověřeno na replayi: fill přišel na `3818.25`, tedy v cenách grafu. Sim plní
z replayovaných dat, ne z živého trhu daného kontraktu. Back-adjustment tedy vypínat nemusíš.

Po každém `-1` zůstane objednávková vrstva zamčená (`STOPPED` ve status boxu). Odemkne ji
jedině **změna** Inputu 5 *Reload Presets* — z Yes na No, nebo z No na Yes. Nastavit ho na to,
co už tam je, nedělá nic.

### Co studie nastavuje za tebe

Tyhle tři věci si studie nastavuje sama a jsou nutné pro to, aby kniha vůbec mohla držet víc
presetů najednou. Jsou tu proto, aby bylo jasné, co se děje, ne aby se měnily:

| ACSIL | Hodnota | Proč |
|---|---|---|
| `sc.AllowEntryWithWorkingOrders` | `1` | Každý preset po prvním jde ven, když už pracují stopy a targety těch předchozích. Sierra to má **defaultně zakázané** — bez toho se vyplní první vstup seance a všechny další se odmítnou. |
| `sc.CancelAllOrdersOnEntriesAndReversals` | `0` | Sierra sama radí tohle zapnout při připojených příkazech, ale ta rada počítá s **jednou** pozicí. Tady odprodej přebytku zavírá jeden preset z deseti a „zruš všechny příkazy" by sebralo stop zbývajícím devíti. |
| `sc.MaximumPositionAllowed` | Max Gross ÷ multiplikátor | Max Gross se počítá v **MES ekvivalentech**, tohle v **kontraktech obchodovaného instrumentu**. Na ES se to liší 10×. |

Než to pustíš naostro, projeď *Mode = Semi-auto*. Ten nic neposílá, jen do Message Logu píše,
co by udělal — jeden řádek na každý vstup, s jeho vlastním stopem a targetem, a jeden souhrnný
na odprodej přebytku:

```
Multi-Swing SEMI: would BUY 1 for LMT_RSIx<x_xAT_1, stop 4812.50 target 4901.25
Multi-Swing SEMI: would BUY 1 for C<wvwapxsd_2, stop 4808.75 target 4890.00
Multi-Swing SEMI: would SELL 2 to hold 7 contracts.
```

Počítá to proti pozici, kterou **předstírá**, že drží — skutečná se nehýbe, když se nic
neposílá, takže by jinak každý řádek hlásil nákup celé knihy místo jednoho denního doobchodu.

Co na těch řádcích čekat:

- **`stop 0.00` není chyba.** 13 ze 48 presetů má čistě signálový exit (`IBS>0.8`, `C>PrevHigh`,
  `C>SMA10`, `Time1`…) a žádný stop-loss nemá, protože se tak ověřily. U nich se posílá vstup bez
  připojeného stopu a kniha je zavře signálem. `target 0.00` platí stejně pro presety, které mají
  SL, ale žádné RRR. Ostatní presety nenulový stop mít musí.
- **`would SELL x to hold y`** je srovnání pozice, ne chyba. Prodává se rozdíl proti tomu, co kniha
  chce držet, a jen tudy odcházejí výstupy `signal` a `time` — tedy 61 % všech výstupů knihy.
- **Součet kontraktů** musí odpovídat *Risk Unit* × váha rodiny za každý otevřený preset. Řádek
  `book ... position ...` ve status boxu ukazuje totéž průběžně.

Řádky najdeš v *Window → Message Log*. Potřebuješ k tomu *Trading Enabled* = Yes,
*Mode* = Semi-auto a *Log Level* = Info (výchozí).

Píše se jen při **změně** cílové expozice, takže v klidných obdobích je log tiše — to je
v pořádku.

**Semi-auto se dá pustit i v Replayi**, a je to nejrychlejší způsob, jak ho vidět na letech dat
místo na jednom dni: nastavení je stejné jako v kapitole 8, jen *Mode* = Semi-auto. Ledger se
přitom píše dál, takže jeden běh zvládne paritu i kontrolu sizingu.

**Co semi-auto neověří.** Nesahá na účet, takže neřekne nic o tom, jestli Sierra po odprodeji
přebytku nechá zbývajícím vstupům jejich připojené stopy. To ukáže až Sim účet níže a je to
první věc, kterou tam kontrolovat: v *Trade → Trade Orders and Positions* musí být otevřených
stop příkazů právě tolik, kolik je otevřených presetů se stopem.

**Plný přepočet grafu.** Sierra během přepočtu příkazy odmítá (`-8998`,
`SCT_SKIPPED_FULL_RECALC`) a má pravdu: studie, která přepočítává roky historie, nesmí tu
historii vystřelit na účet. Studie se to **nesnaží předvídat** — příkaz nabídne a rozhodnutí
nechá na Sierře. Když ho Sierra přeskočí, nezapočítá se to do limitu odmítnutých příkazů (na
účet se nic nedostalo, takže se nic nerozešlo) a zbytek volání se zahodí, takže jedno
odmítnutí stojí jednu řádku v logu místo osmačtyřiceti.

Dřív studie hádala podle `sc.UpdateStartIndex` a byla to chyba: **chart replay přepočítává graf
na každém baru**, takže tím guardem se order vrstva na celý replay umlčela.

Počítej s tím, že až Sierra příkazy pustí, může naráz odejít i deset kusů — tolik presetů kniha
z historie drží otevřených. To je záměr, ne chyba: účet má držet to, co kniha.

### Replay pro obchodování vs. pro paritu

Nastavení se **liší** podle toho, co testuješ:

| | Parita (kapitola 8) | Obchodování na Simu |
|---|---|---|
| Mode | Signals only | Full auto |
| *Clear chart before replay* | **zapnuto** — čistý start | **vypnuto** — graf si nechá načtenou historii |
| Replay Speed | Maximum | 50× až 200× |
| *Replay Mode* | Standard | zkus volbu pro back-test obchodních systémů, pokud ji tvoje verze má |

**Proč vypnout *Clear chart before replay*:** s ním graf začíná prázdný a staví se od baru 1, takže
studie ztratí všech 400 seancí zahřátí a Sierra přepočítává minimální pole. Bez něj replay historii
dopisuje, přepočty přestanou a signály jdou hned.

**Proč ne Maximum:** simulované fily nemusí stíhat a testoval bys něco jiného, než co se stane
naostro.

**Než pustíš full auto, nastav limity ztrát.** Inputy 38 a 39 už fungují (kapitola 5), ale
výchozí nula je vypíná. Spolu s 34 *Max Gross Exposure* jsou to jediné tři stropy, které
na účtu drží.

### Co uvidíš v logu

```
Multi-Swing: FULL AUTO, orders ARE being sent to the trade service.
Multi-Swing: BUY 1 IBS<x_1  stop 5812.50  target 5934.75
Multi-Swing: STOP MOVED for IBS<x_1 from 5812.50 to 5868.25 (order 41207)
Multi-Swing: SELL 2 -> position 7 (book wants 7)
```

Řádek `STOP MOVED` je trailing nebo breakeven: studie najde připojený stop přes
`sc.GetAttachedOrderIDsForParentOrder` a přesune ho `sc.ModifyOrder`. **Posouvá se jen nahoru.**
Žádá o to právě 8 ze 48 presetů — ty, které mají v `swing_presets.csv` ve sloupci `exit`
`Trail` nebo `BE`. Když se posun odmítne, zaloguje se to jako chyba, ale vstupy se nezastaví:
v trhu zůstává původní, širší stop, takže pozice je pořád chráněná.

Odmítnutý příkaz se loguje jako chyba **pokaždé**, ne jen jednou. Má to důvod: po odmítnutí
drží účet něco jiného, než si myslí ledger, a každé další dorovnání se počítá proti špatné
pozici. Když ti to naskakuje, zkontroluj vybraný účet a Trade Simulation Mode.

**Po pěti odmítnutích studie přestane posílat** a status box zšedne na
`STOPPED - rejections, nothing is being sent`. Je to schválně: dál posílat příkazy proti
pozici, o které studie neví, co v ní je, je horší než přestat. Hláška v logu u každého
odmítnutí nese **návratový kód Sierry** (`Sierra returned -X`) — to je to jediné číslo, které
řekne proč, takže si ho najdi.

Zrušit ten stav jde **přepnutím Inputu 5 *Reload Presets*** tam a zpět: přenačte knihu od
prvního baru a zahodí i pohled order vrstvy na účet. Než to uděláš, **srovnej pozici na účtu
ručně na nulu**, jinak se studie bude srovnávat proti něčemu, co nezavedla.

### Nekompletní seance

Studie hlídá, jestli každá seance došla až ke svému RTH konci. Když ne, napíše do Message Logu:

```
Multi-Swing: INCOMPLETE SESSION 2023-08-09 - last RTH bar at 15:35, RTH ends at 16:00,
and no exchange half day closes then. The close used is 5268.00, ...
```

a ve status boxu přibude řádek `WARNING  n incomplete sessions`. **Ber to vážně:** close, ze
kterého se ten den počítají signály, není close seance, a jde dál do ATR20 a klouzavých
průměrů na dalších zhruba dvacet seancí. Právě tohle se stalo při tvém replayi 2023-08-09 —
jedna seance useknutá v 15:35 rozhodila 26 vstupů na pěti dnech.

Nejčastější příčina je **zastavení a znovuspuštění replaye uprostřed seance**. Když se to
stane, pusť ten úsek znovu vcelku.

Plánované půldny (13:00 a 13:15) se **nehlásí** — studie je pozná podle času a jsou v pořádku,
offline engine je vidí stejně. Ověřeno na letech 2015–2026: 99 zkrácených seancí, všechny ve
12:59, 13:00 nebo 13:14, ani jedna falešně nahlášená.

### Na co pozor

- *Max Gross Exposure* (Input 34) je zároveň strop pro `MaximumPositionAllowed`. Výchozích 60
  odpovídá 1 MES na preset. Na ES to přepočítej, jeden ES je deset MES.
- *Flatten At Session End* nech **No**. Jsou to swingy, přes noc se drží.
- Replay se Simem obchoduje proti přehrávaným barům, takže si můžeš celý rok proobchodovat
  za pár minut. Fily jsou ale simulované — o skutečném slippage nevypovídají nic.

---

## Časté chyby

| Příznak | Příčina |
|---|---|
| Žádné signály, log je v pořádku | *Trading Enabled* je na No, nebo je načteno málo dní |
| VWAP čáry jsou na nule | graf nemá objemy, nebo je to non-intraday graf |
| Signály na jiných dnech než v backtestu | graf není *Back Adjusted*, nebo je jiná časová zóna |
| Replay dá zhruba dvojnásobek obchodů od data startu | studie z verze před opravou live guardu — přebuildi DLL |
| Rozdíl jen v rodinách `C<wvwap#sd` a `D01` | studie z verze, kde týdenní VWAP kotvil na středu místo pondělí — přebuildi DLL |
| Ledger má dvakrát tytéž obchody | starý soubor z verze před touto opravou, smaž ho |
| Všechny příkazy odmítnuty s `Sierra returned -8998` | `SCT_SKIPPED_FULL_RECALC` — studie posílala příkazy během plného přepočtu grafu, což Sierra zásadně odmítá. Opraveno; přebuilduj DLL |
| Všechny příkazy odmítnuty s `Sierra returned -1` | Obecné odmítnutí, **důvod píše Sierra jinam** — *Trade → Trade Activity Log* a řádky v Message Logu **bez** prefixu `Study:`. Nejčastěji vypnutý *Trade Simulation Mode* bez připojeného účtu, nezapnuté auto trading, nebo nevybraný Trade Account |
| Ceny stopů a targetů v logu nejsou na ticku | verze před opravou zaokrouhlování; přebuilduj DLL |
| `check_replay.py` hlásí 0/48 shodných vstupů | ledger je ze staré verze studie, která psala datum v zobrazovacím formátu Sierry — přebuildi DLL |
