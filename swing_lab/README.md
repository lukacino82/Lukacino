# ES Multi-Swing Lab

Výzkumný framework pro swingové systémy na ES futures. Zapojitelné systémy (setup × režim × exit × směr),
masivní grid, vícestupňové síto, walk-forward, kanonické publikované systémy a portfolio s přepínači ANO/NE.

Report: `results/ES_SWING_LAB_REPORT.html`

## Data
- `ES3000` (1min, 2018-07 → 2026-09, bid/ask) – neupravené kontrakty, roll gapy každé čtvrtletí.
- Excel `List1` (volume bary, 2016-07 → 2026-07, back-adjusted) – slouží ke kalibraci rollů a jako historie 2016–2018.
- Roll prémie = skok rozdílu Excel − ES3000 přes rollový víkend (přesně, víkendový pohyb se odečte). Aditivní back-adjust ke
  poslednímu kontraktu → P&L v bodech je přesný na 1 kontrakt. Sep-2026 roll odhadnut (průměr 4 posledních).

## Pipeline
```
pip install pandas numpy numba scipy pyarrow openpyxl
python data_prep.py      # zipy -> swing_lab/data/es1m_adj.parquet (+ rolls.csv)
python features.py       # denní feature matrix + 30min bary
python grid.py [--wf]    # 270k systémů (~90 s na 4 jádrech)
python sieve.py          # funnel + stage-3 robustnost
python select_portfolio.py [--wf]   # diverzifikovaný výběr + slepý test
python ensemble.py [--wf]           # rodinné ensembly
python canonical.py      # publikované systémy s pevnými parametry
python portfolio.py      # kniha dle portfolio_config.json
python report_data.py && python build_report.py
```

## Moduly
| soubor | obsah |
|---|---|
| `engine.py` | numba engine: vstup close / next open / limit / stop; SL, TP, RRR, ATR, trailing, breakeven, time stop, signálový exit; stopky i v overnight segmentu; TP+SL ve stejném segmentu řešeno na 30min barech (SL první) |
| `features.py` | RTH + overnight segmenty, VWAP denní/týdenní/měsíční/kvartální/roční ± σ, VWAP minulých period, delta, kumulativní delta, volume profil (den, týden), RSI/MA/ATR/IBS/%b/ADX, kalendář |
| `systems.py` | registr: 152 setupů, 11 režimů, 156 exitů (long + zrcadlové shorty) |
| `lab.py` | statistiky, B&H benchmark (vč. rolů), alfa regrese, periody Discovery/Validation/OOS |
| `sieve.py` | síto: edge → alfa vs B&H → robustnost (náklady 1,5, zpoždění, plató, Monte Carlo) → Deflated Sharpe |
| `canonical.py` | Connors RSI(2), kumulativní RSI, Double 7s, 4 down dny, %b, IBS, Turnaround, TOM, pre-holiday, Faber |
| `portfolio.py` + `portfolio_config.json` | kniha systémů, `enabled: yes/no`, `contracts` (0,1 = 1 MES) |

## Hlavní závěry (podrobně v reportu)
1. In-sample výběr (Sharpe 2,11) je overfit – walk-forward výběr prohrál s B&H ve slepém období 2022–26 ve 4 verzích.
2. Žádný jednotlivý systém neprojde Deflated Sharpe (max 0,49).
3. Kanonické publikované systémy mají reálnou edge (8/9 kladné i při 1,5 b. nákladech); kniha 12 212 b. vs B&H 4 556 b.,
   risk-adjusted jen mírně lepší (Sharpe 0,68 vs 0,65).
4. Shorty na ES nefungují. Pevné body TP/SL se mimo vzorek rozpadají, používat ATR. Nejlepší exit = signálový exit do síly.
5. K opravdové robustnosti chybí delší historie (denní SPX 1990+) a forward test.
