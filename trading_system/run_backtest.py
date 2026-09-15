"""CLI entry point for the backtest harness (trading_system/backtest/replay.py).

Run against a real, accumulated ``daily_profile_export.csv`` (the same file
ACSIL appends to live -- just point this at a copy with weeks/months of
history) and a historical intraday CSV in the same column shape as
``live_state.csv`` but with many rows instead of one (e.g. built by logging
every ``live_state.csv`` refresh over time, or exported from Sierra Chart and
converted separately -- there's no ACSIL-side "historical VWAP/delta export"
yet, see ARCHITECTURE.md's backtest step)::

    python -m trading_system.run_backtest \\
        --instrument NQ \\
        --daily-profiles path/to/daily_profile_export.csv \\
        --intraday-history path/to/historical_intraday.csv

Reuses run_live.py's INSTRUMENT_CONFIGS so a backtest and the live process
are always checked against the exact same thresholds -- there's deliberately
no separate "backtest config" an instrument could drift out of sync with.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .backtest.replay import BacktestConfig, BacktestReport, run_backtest
from .bridge.csv_bridge import read_daily_profiles, read_live_state_history
from .run_live import INSTRUMENT_CONFIGS


def _print_report(instrument: str, report: BacktestReport) -> None:
    resolved = report.resolved
    print(f"{instrument}: {len(report.trades)} trade(s) ({len(resolved)} resolved, "
          f"{len(report.trades) - len(resolved)} still open at end of data)")
    print(f"  skipped (actionable but no target_1 to judge): {report.skipped_no_target}")
    if not resolved:
        print("  no resolved trades -- nothing to score yet")
        return
    print(f"  wins: {len(report.wins)}  losses: {len(report.losses)}  "
          f"win rate: {report.win_rate:.1%}")
    print(f"  total R: {report.total_r:+.2f}  average R: {report.average_r:+.2f}")
    for trade in report.trades:
        outcome = trade.status.value.upper()
        r_str = f"{trade.r_multiple:+.2f}R" if trade.r_multiple is not None else "n/a"
        print(f"    {trade.opened_at.isoformat()}  {trade.hypothesis_type.value:8s} "
              f"{trade.direction:5s} entry={trade.entry:.2f} stop={trade.stop:.2f} "
              f"target_1={trade.target_1:.2f}  -> {outcome} ({r_str})")


def run(instrument: str, daily_profiles_path: Path, intraday_history_path: Path) -> BacktestReport:
    if instrument not in INSTRUMENT_CONFIGS:
        known = ", ".join(sorted(INSTRUMENT_CONFIGS)) or "(none configured)"
        raise ValueError(
            f"No InstrumentConfig for {instrument!r} in run_live.py's INSTRUMENT_CONFIGS "
            f"(configured: {known}) -- add one there first, same as for running live."
        )
    live_config = INSTRUMENT_CONFIGS[instrument]
    config = BacktestConfig(
        sizing=live_config.sizing,
        price_move_threshold=live_config.price_move_threshold,
        delta_move_threshold=live_config.delta_move_threshold,
        gap_threshold_fraction=live_config.gap_threshold_fraction,
        delta_imbalance=live_config.delta_imbalance,
    )

    daily_profiles = read_daily_profiles(daily_profiles_path)
    intraday_states = read_live_state_history(intraday_history_path)

    report = run_backtest(instrument, daily_profiles, intraday_states, config)
    _print_report(instrument, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--daily-profiles", required=True, type=Path)
    parser.add_argument("--intraday-history", required=True, type=Path)
    args = parser.parse_args()
    run(args.instrument, args.daily_profiles, args.intraday_history)
