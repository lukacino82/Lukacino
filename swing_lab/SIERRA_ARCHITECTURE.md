# Lukacino Multi-Swing — Sierra Chart architektura

Návrh ACSIL studie pro 12 rodin z `results/ES_CORRECTION_ALPHA.html`. Zdroj pravdy pro
implementaci; když se rozhodnutí změní, uprav tento soubor, ne chat.

## Proč ne stejná architektura jako ORB_RRR / TradingHypothesisStudy

| | ORB_RRR.cpp | TradingHypothesisStudy.cpp | Multi-Swing (tento návrh) |
|---|---|---|---|
| Strategií na studii | 1 | 1 | **48 presetů ve 12 rodinách** |
| Kde jsou pravidla | v Inputs | v Inputs + kódu | **v CSV configu** |
| Inputs | 14 | ~50 | ~50 |
| Kdo drží pozici | studie | studie | **jeden controller** |

Zásadní zjištění výzkumu je, že rodina musí obchodovat jako **ensemble několika variant**, nikdy
jako jeden nejlepší parametr. Jeden nejlepší parametr byl přesně to, co ve všech předchozích
verzích mimo vzorek selhalo. Z toho plynou dvě architektonická omezení:

1. **48 presetů se nevejde do Inputs.** Při 6 Inputech na strategii (`Enabled`, `Direction`,
   `Risk Weight`, `Signal Preset`, `Entry Profile`, `Exit Profile`) je to 288 Inputů proti limitu
   128. Proto definice strategií čte studie z textového souboru a Inputs řídí jen globální chování
   a zapínání rodin.
2. **Packy podle rolí nemohou každý posílat příkazy.** Pozice v Sierra Chart je na úrovni
   symbolu a účtu. Kdyby osm packů posílalo příkazy na stejný ES, vzájemně by si netovaly pozice a
   žádný by neznal svou skutečnou expozici. Proto je to **jedna studie, která vlastní pozici**,
   a role jsou uvnitř ní.

Styl nastavení (přepínač režimu, `Send Orders To Trade Service` jako samostatná pojistka,
pojmenované skupiny Inputů, kill na konci seance) z tvých existujících skriptů zůstává, protože
funguje a znáš ho. Mění se jen to, odkud se berou definice strategií.

## Toky dat

```text
swing_lab (Python)                    Sierra Chart
─────────────────                     ────────────
grid.parquet                          Lukacino_MultiSwing.cpp
   │ export_presets.py                   │
   ▼                                     │  čte při startu a na Reload
swing_presets.csv  ────────────────────► │
                                         ├─ FeatureEngine   denní RTH bary + ATR/RSI/IBS/VWAP/MA/DD
                                         ├─ SignalEngine    48 presetů → armed / triggered
                                         ├─ RiskController  cap na rodinu, roli i celek
                                         ├─ OrderManager    vstupy, SL/TP, trailing, time stop
                                         └─ Journal         CSV ledger pro srovnání s backtestem
```

`swing_presets.csv` má jeden řádek na preset a sloupce
`id, family, role, variant, setup, regime, exit, trades, win, avg_pts, pf, sharpe, hold_days, exposure`.
Studie parsuje `setup`, `regime` a `exit` do vnitřních enumů. Tím je zaručeno, že backtest a živý
provoz obchodují doslova stejná pravidla; každá změna pravidel začíná v Pythonu a projde sítem.

## Sizing

48 presetů má dohromady průměrnou expozici 9,5 ES ekvivalentu, špičkově zhruba 4–5× tolik.
Základní jednotka je proto **1 MES na preset**: průměrně 0,95 ES, ve špičce kolem 4,8 ES.
Kdo chce jet v ES, škáluje `Risk Unit` a musí zvednout `Max Gross`.

## Inputs (cíl 52, limit 128, rezerva 76)

Indexy jsou pevné. Nový Input se přidává **jen na konec**, zrušený zůstává jako `Reserved`,
aby se uživatelům nerozsypalo uložené nastavení.

### 0–9 Global

| # | Input | Typ | Default | Poznámka |
|---|---|---|---|---|
| 0 | Trading Enabled | Yes/No | No | hlavní vypínač, nic se neposílá |
| 1 | Mode | Custom | Signals only | `Signals only; Semi-auto (alerty + připravený příkaz); Full auto` |
| 2 | Send Orders To Trade Service (LIVE!) | Yes/No | No | druhá nezávislá pojistka, nikdy defaultně zapnutá |
| 3 | Direction Filter | Custom | Long only | `Long only; Both; Short only` |
| 4 | Preset File Path | String | `swing_presets.csv` | relativně k Data Files Folder |
| 5 | Reload Presets | Yes/No | No | přepni sem a zpět = načtení bez restartu |
| 6 | Risk Unit (contracts per preset) | Float | 1 | 1 = 1 MES na preset |
| 7 | Instrument Multiple | Custom | MES | `MES; ES` — jen pro přepočet a kontrolu ticku |
| 8 | Evaluate At | Custom | RTH close −1 min | `RTH close −1 min; RTH close; Next RTH open` |
| 9 | Journal CSV | String | `swing_journal.csv` | ledger pro trade-by-trade srovnání s backtestem |

### 10–21 Rodiny (zapínání a váha)

Dvanáct rodin, dva Inputy na rodinu: `Enabled` a `Weight`. Váha násobí `Risk Unit`, takže se dá
rodina ztlumit bez vypnutí. Rodiny v pořadí podle alfa t-statistiky z výzkumu:

| # | Rodina | alfa t | Default |
|---|---|---|---|
| 10–11 | Limit pullback po oversold RSI | 3,03 | On, 1,0 |
| 12–13 | Close pod denním VWAP − kσ | 2,17 | On, 1,0 |
| 14–15 | Close pod týdenním VWAP − kσ | 2,12 | On, 1,0 |
| 16–17 | Reclaim krátké MA po drawdownu | 2,08 | On, 1,0 |
| 18–19 | Drawdown od 20/50d high + RSI(2) | 2,01 | On, 1,0 |
| 20–21 | IBS (close u denního low) | 2,01 | On, 1,0 |

Zbývajících šest rodin (%R, VWAP pásmo D01, N-denní low, RSI oversold, drawdown + IBS,
Connors RSI) sdílí Inputy 22–33 podle stejného vzoru.

### 34–41 Risk controller

| # | Input | Default | Proč |
|---|---|---|---|
| 34 | Max Gross Contracts | 60 MES | tvrdý strop celkové expozice |
| 35 | Max Concurrent Presets | 24 | brání tomu, aby se ve velké korekci spustilo všech 48 najednou |
| 36 | Max Per Family | 4 | rodina nikdy neváží víc než svůj ensemble |
| 37 | Max Per Role | 12 | šest rolí, aby jedna nepřevážila knihu |
| 38 | Daily Loss Limit (USD) | 0 = off | po překročení jen zavírá |
| 39 | Max Drawdown Stop (USD) | 0 = off | vypne `Trading Enabled` a zaloguje důvod |
| 40 | Correction Scale-In | Yes/No | No | při DD > 5 % 1,5×, > 10 % 2×, jinak 1× |
| 41 | Scale-In Cap | 2,0 | strop pro předchozí bod |

### 42–47 Exekuce

| # | Input | Default |
|---|---|---|
| 42 | Entry Order Type | `Market on next open; Limit at preset level; Stop above prev high` |
| 43 | Limit Offset (ticks) | 0 |
| 44 | Entry Expiry (sessions) | 1 — nevyplněný limit se ruší, nikdy se nemění na market |
| 45 | Max Slippage (ticks) | 8 — nad to se vstup zahodí a zaloguje |
| 46 | Flatten At Session End | No — swing drží přes noc, proto default No |
| 47 | Global Time Stop (sessions) | 20 |

### 48–51 Reference na studie a diagnostika

| # | Input |
|---|---|
| 48 | Weekly VWAP Study ID (0 = počítat interně) |
| 49 | Monthly VWAP Study ID (0 = počítat interně) |
| 50 | Log Level (`Errors; Info; Debug trace per preset`) |
| 51 | Draw Signals On Chart |

Delta a value area zatím Inputy nemají: `F` rodiny podle výzkumu nevydělávají a `E` rodiny čekají
na skutečný VAP export. Až přijdou, dostanou indexy od 52 výš.

## Exit profily

Každý preset si nese svůj exit ve sloupci `exit` a studie je parsuje na tyto profily:

| Profil | Zápis v CSV | Parametry |
|---|---|---|
| Signálový exit | `x:C>SMA5`, `x:RSI2>70`, `x:IBS>0.8`, `x:C>PrevHigh`, `x:C>wvwap` | volitelně `+SL{k}ATR`, `+T{n}` |
| ATR bracket | `x:SL{k}ATR_RRR{r}` | SL = k × ATR20, TP = SL × r |
| Breakeven | `x:SL{k}ATR_RRR{r}_BE{b}R` | stop na vstup + náklady po MFE ≥ b × R |
| Trailing | `x:Trail{k}ATR_act{a}R` | chandelier k × ATR, aktivace po a × R |
| Time stop | `x:Time{n}` | n dokončených seancí |

Trailing se smí jen utahovat, nikdy povolovat, a nová úroveň platí až od dalšího baru — stejně
jako v `engine.py`, aby replay seděl na backtest.

## Parita s backtestem

Aby šlo tvrdit, že živý provoz dělá totéž co výzkum:

1. Signál se počítá jen z **dokončených RTH denních barů**, vyhodnocení v čase podle Inputu 8.
2. Při současném zásahu SL a TP v jednom baru se počítá **SL první**.
3. ATR20 a MA se počítají z dokončených RTH denních seancí, ne z ETH.
4. Studie zapisuje ledger (`Journal CSV`) se stejnými sloupci jako `lab.trades_df`.
5. Před ostrým provozem se pustí Sierra Replay přes 2018–2026 a ledger se porovná
   obchod po obchodu s `swing_lab`. Rozdíl nad 1 tick na obchod je chyba implementace.

## Pořadí prací

1. `Lukacino_MultiSwing.cpp` — kostra, parser CSV, FeatureEngine, kreslení signálů, `Mode = Signals only`.
2. Parita: replay 2018–2026 proti Python ledgeru.
3. OrderManager a RiskController, stále `Send Orders To Trade Service = No`.
4. Semi-auto na simulovaném účtu, minimálně 50 obchodů nebo 6 měsíců.
5. Teprve potom živý kapitál, podle produkční brány v `CORRECTION_ALPHA_BLUEPRINT.md`.
