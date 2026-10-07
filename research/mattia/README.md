# ES Alpha Map (Mattia strategies + systematic families)

Tests on ES2008 1-minute back-adjusted data (2008-05 .. 2026-09, ET):

* `strategies.py` - the three prop-firm strategies from the Mattia Kanti interview (Vault Break,
  VWAP Pullback + ADX, Overnight Bias ORB), ported from NQ to ES.
* `families.py` - overnight drift, walk-forward hour-of-day bias, intraday momentum (Gao 2018),
  noise-area momentum (Zarattini et al. 2024), calendar effects, IBS, vol-managed / trend /
  drawdown exposure overlays and an approximation of the ChatGPT "crisis allocator".
* `m_run1.py` .. `m_run8.py` - the experiments (outputs in `out/run*.txt`, grids in `out/*.csv`).
* `report.py` + `report_template.html` -> `out/report.html`.

Data: rebuild `/tmp/claude-0/data/es2008.parquet` from `ES2008.z01..z04 + ES2008.zip` (main branch),
then run `m_run1.py` (builds the bar cache and ADX), `m_run7.py` (daily series) and `report.py`.
