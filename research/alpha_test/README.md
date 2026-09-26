# ES alpha test

Independent backtest of every strategy from `alpha brainstorm.zip` (Phase 1–4) plus the
Open ± X system, on ES3000 1-minute data (2018–2026) and the Excel volume bars (2016–2026).

Reproduce (the raw data are the split zips in the repo root):

```
pip install pandas numpy numba pyarrow openpyxl
# unpack ES3000.zip/.z01/.z02 and "es mini data new 2 (2)" to /tmp/claude-0/data, convert to parquet
python build.py      # sessions + features cache
python run.py        # all strategies, TP/SL grids, walk-forward, Open ± X grid
python finalize.py   # robustness gates G1–G7, verdicts, benchmarks
python report.py     # out/report.html
```

Main outputs: `out/summary.csv` (verdict per strategy), `out/trades.csv`, `out/openx.csv`,
`out/grid.csv`, `out/exp_in_atr_units.csv`, `out/report.html`.
