# import_sierra_ohlcv_bars.py

Converts Sierra-Chart-exported 1-minute OHLCV bars (`Date, Time, Open, High,
Low, Last, Volume, NumberOfTrades, BidVolume, AskVolume`) into this repo's
bridge CSV shapes (`daily_profile_export.csv` + `historical_intraday.csv`),
so `run_backtest.py` can run against real historical data instead of only
live ACSIL-captured history. See the module docstring for exactly how
VWAP/SD-bands/delta/volume-profile are approximated from raw bars.

```
python3 import_sierra_ohlcv_bars.py <input.txt> <tick_size> <out_dir>
```

## Provenance of the first real run

Source data: `ES2008.zip` (+ `.z01`-`.z04`), a 1-minute-bar export covering
`2008-05-04` through `2026-09-25` for a back-adjusted continuous ES
contract, confirmed present in this repo's `chatgpt-es2008-research` branch
and on the user's own Google Drive. 6,439,575 bars.

## Known gap vs. the real methodology

`DailyProfile.volume_at_price` is left `None` here (POC/VAL/VAH are
computed internally but not kept as the full per-price histogram), so
`CompositeEngine`'s merge check (`composite/overlap.py`'s
`overlap_fraction`, default 60% threshold) falls back to a plain
value-area *price-range* overlap instead of the true volume-weighted
overlap the methodology calls for ("at least 60% of a day's transactions
happened in the shared zone"). Wiring `day_hist` (already computed
per-day inside the converter for POC/VAL/VAH) into `DailyProfile.
volume_at_price` would close this gap -- not done yet, flagged for the
next real run.

## Results (first full run, 2026-10-08)

ES, full file, after the `tiers.py` tolerance fix (see that commit):

- 2,743,712 ticks reached `engine.tick()` (the rest were spent managing
  an already-open trade -- see `backtest/replay.py`'s "one trade at a
  time" rule), 36,604 trades.
- wins=15,700 losses=20,903 (42.9% win rate), total R=+2,647.00,
  average R=+0.07/trade.
- By hypothesis type (trades / win rate / total R): A long 1043/42.8%/+72,
  A short 831/40.3%/+6.5, B long 7978/43.6%/+710.5, B short
  7181/40.3%/+46.5, Counter long 12196/44.7%/+1419, Counter short
  7375/42.1%/+392.5.
- Counter long/short (the multi-timeframe synthesis model, ARCHITECTURE.md
  item 8) accounts for more than half of total R despite no transaction
  cost modeling in this harness -- a real edge signal, not proof of a
  deployable strategy on its own.
- Full trade-by-trade log (36,604 lines) was 3.6MB, too large to commit
  here -- regenerate with the command above against the daily/intraday
  CSVs (also not committed, ~1GB) built from the source ZIP.
