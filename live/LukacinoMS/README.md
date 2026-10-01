# LukacinoMS Live Performance

This folder is the canonical GitHub source for the continuously updated LukacinoMS trade log.

## Source of truth
- `LukacinoMS_trades.csv`

The CSV can be overwritten/updated whenever Sierra Chart or another export process adds new completed trades.

## Expected columns
```text
System,EntryDate,ExitDate,Dir,Qty,EntryPrice,ExitPrice,Points,PnL,HoldDays,Reason
```

EntryDate and ExitDate are currently Excel serial dates. Convert with origin `1899-12-30`.

## Equity calculation
- Sort completed trades by ExitDate, then EntryDate.
- Realized equity = cumulative sum of `PnL`.
- Drawdown = realized equity minus running peak.
- Keep separate curves for each `System`.
- Do not silently alter historical rows.
- If an export is corrected, treat the newest CSV as canonical and recompute the whole report.

## Current systems
- VAL Swing
- Lower Closes
- Capitulation
- RSI(2)

## ChatGPT workflow
When asked to update the equity:
1. Fetch the latest `live/LukacinoMS/LukacinoMS_trades.csv` from GitHub main.
2. Compare with the prior analyzed version if available.
3. Report newly added/changed trades.
4. Recalculate overall equity, system equities, drawdown, PF, win rate, expectancy and holding-time stats.
5. Flag material deterioration or improvement by system.

## Recommended Sierra export workflow
Point Sierra's automated export/sync process at this file through a local Git checkout or an external sync script. GitHub itself is not a live filesystem; changes become visible here only after a commit/push.
