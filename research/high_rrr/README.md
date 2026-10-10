# ES Loss Streak Lab (high reward:risk research)

* `engine.py` - 1-minute outcome scan: one pass per entry gives every stop (points) x RRR result,
  EOD and 5-day horizons; single-position sequencing and streak statistics.
* `context.py` - entry events (30-min grid, VWAP D/W/M touches, 5-day composite VAL/VAH, n-th
  test of 6.5 h / 1 day / 5 day low-high, sweeps) and context (regime, drawdown, RSI D/W/M,
  flat VWAPs, VWAP location, composite VA, balance, time of day, number of tests).
* `build.py` -> `/tmp/claude-0/data/hr_scan.pkl`; `analysis.py` (baseline grid);
  `search.py real|null1` (single + pair filters, shuffled-context null); `summary.py`;
  `trail.py` + `extra.py` (exit variants, pause rules, streak frequencies, SL vs ATR);
  `streaks_where.py`, `corr_filter.py`; `report.py` -> `out/report.html`, `make_pdf.js`.
