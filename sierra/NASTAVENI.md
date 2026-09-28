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

1. `Lukacino_MultiSwing.cpp` → `SierraChart\ACS_Source\`
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
| Symbol | Continuous Futures Contract | **Date Rule Rollover – Back Adjusted** | bez toho zkreslí rollové skoky ATR i drawdown |
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
| 7 | Instrument | MES | přepni na ES, když jedeš velké kontrakty |
| 8 | Evaluate Signals At | RTH close | nech, odpovídá výzkumu |
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

| # | Input | Výchozí | Poznámka |
|---|---|---|---|
| 34 | Max Gross Contracts | 60 | strop v MES; při Risk Unit 1 stačí |
| 35 | Max Concurrent Presets | 24 | z 48 možných, brání nákupu všeho v jedné korekci |
| 36 | Max Presets Per Family | 4 | rodina má právě 4 varianty |
| 37 | Max Presets Per Role | 12 | |
| 38 | Daily Loss Limit (USD) | 0 = vypnuto | zapni až v semi-auto |
| 39 | Max Drawdown Stop (USD) | 0 = vypnuto | zapni až v semi-auto |
| 40 | Scale In By Correction Depth | No | |
| 41 | Scale In Cap | 2.0 | platí jen když je 40 na Yes |

### Exekuce (42–47)

Nech všechno na výchozím. *Flatten At Session End* musí zůstat **No** — jde o swingy,
které drží přes noc.

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

1. *Chart Settings → Days to Load* = **3300** (pokryje 2018–2026)
2. Počkej, až se data stáhnou, sleduj *Window → Message Log*
3. *Chart → Replay Chart* → Start Date **2018-01-01**, rychlost **Maximum**, *Replay Mode: Standard*
4. Nech doběhnout až do konce
5. Pošli mi `swing_journal.csv` z Data Files Folder

Porovnám ho s výzkumným ledgerem obchod po obchodu. Offline už teď sedí: 32 ze 48 presetů
má identickou množinu vstupů a P&L je 94,2 % Pythonu. Replay ověří to, co offline test
ověřit nemůže — chování samotné Sierry se seancemi a živými bary.

---

## Časté chyby

| Příznak | Příčina |
|---|---|
| Žádné signály, log je v pořádku | *Trading Enabled* je na No, nebo je načteno málo dní |
| VWAP čáry jsou na nule | graf nemá objemy, nebo je to non-intraday graf |
| Signály na jiných dnech než v backtestu | graf není *Back Adjusted*, nebo je jiná časová zóna |
| Ledger má dvakrát tytéž obchody | starý soubor z verze před touto opravou, smaž ho |
