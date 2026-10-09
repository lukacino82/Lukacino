# ES Edge Factory

One protocol for thousands of hypotheses on ES2008 (1-minute, back-adjusted, 2008-2026).

* `data.py` - 5-minute globex bars, anchored VWAPs (RTH/globex/week/month), delta and CVD,
  daily table with calendar fields (OPEX, holidays, FOMC 2016+, lunar phase). Cached to
  `/tmp/claude-0/data/ef_cache.pkl`, built from `/tmp/claude-0/data/es2008.parquet`.
* `factory.py` - evaluation: forward returns, same-time-of-day/same-year null, non-overlap,
  direction set in DISC 2008-16, confirmation in VAL 2017-21 and TEST 2022-26, BH-FDR 10 %.
* `hypotheses.py` - families: calendar, time windows, VWAP retests and bands, volume shocks and
  absorption, CVD divergences (1 h .. 1 year), stop-hunt sweeps, crowd patterns, opening drive.
* `run_factory.py` -> `out/factory_results.csv`; `diagnostics.py` -> `out/family_diag.csv`.
* `ml.py`, `ml_daily_strategy.py` - LightGBM walk-forward on 60 state features.
* `money.py` - Kelly / bankroll tables, Monte Carlo of sizing schemes, RSI(2) vs placebo, A-setups.
* `report.py` + `report_template.html` -> `out/report.html`; `make_pdf.js` -> `out/ES_Edge_Factory.pdf`.
