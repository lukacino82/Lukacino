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

from .backtest.replay import BacktestConfig, BacktestReport, GroupStats, run_backtest
from .bridge.csv_bridge import read_daily_profiles, read_live_state_history
from .run_live import INSTRUMENT_CONFIGS


def _print_group_line(label: str, stats: GroupStats) -> None:
    if stats.open_count == stats.trades:
        print(f"    {label:10s} {stats.trades} trade(s), all still open -- nothing resolved yet")
        return
    win_rate = f"{stats.win_rate:.1%}" if stats.win_rate is not None else "n/a"
    print(f"    {label:10s} {stats.trades} trade(s)  wins={stats.wins} losses={stats.losses} "
          f"open={stats.open_count}  win rate={win_rate}  total R={stats.total_r:+.2f}")


def _print_report(instrument: str, report: BacktestReport) -> None:
    total_ticks = sum(report.regime_counts.values())
    print(f"{instrument}: {total_ticks} tick(s) classified "
          f"({len(report.trades)} trade(s), {report.skipped_no_target} skipped -- no target_1)")
    for regime in sorted(report.regime_counts, key=lambda r: r.value):
        count = report.regime_counts[regime]
        share = f"{count / total_ticks:.1%}" if total_ticks else "n/a"
        print(f"    {regime.value:8s} {count} ({share})")

    resolved = report.resolved
    if not report.trades:
        print("  no trades at all -- if UNCLEAR dominates above, "
              "regime.py's threshold (delta_imbalance in run_live.py's "
              "INSTRUMENT_CONFIGS) is too strict for this data, not broken")
        return
    if not resolved:
        print("  no resolved trades -- nothing to score yet")
        return
    print(f"  wins: {len(report.wins)}  losses: {len(report.losses)}  "
          f"win rate: {report.win_rate:.1%}")
    print(f"  total R: {report.total_r:+.2f}  average R: {report.average_r:+.2f}")

    print("  by hypothesis type:")
    for hyp_type, stats in sorted(report.by_hypothesis_type().items(), key=lambda kv: kv[0].value):
        _print_group_line(hyp_type.value, stats)
    print("  by confluence:")
    for confluence, stats in sorted(report.by_confluence().items(), key=lambda kv: kv[0].value):
        _print_group_line(confluence.value, stats)

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
        delta_imbalance=live_config.delta_imbalance,
        rrr=live_config.rrr,
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
