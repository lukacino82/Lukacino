"""Runs LiveEngine over a full real history ONCE (the expensive part --
regime/hypothesis/confluence classification per tick) and records every
actual trade entry with enough context for later, cheap analysis that
doesn't need to re-run the engine:

  - entries.csv: one row per trade, with everything needed for pattern
    mining (day of week, hour, hypothesis type, confluence, HTF bias,
    composite context) AND for an exit-rule sweep (structural stop
    distance, target distances, and an index into prices.bin).
  - prices.bin: every state's last_price, in order, as a flat
    array('d') (~50MB for 6.4M rows vs. ~1GB for the full CSV) -- entries.
    csv's entry_index points into this, so a later TP/SL/RRR sweep can
    scan forward from any entry without touching the full bridge CSV or
    re-running engine.tick() at all.

Entry gating mirrors backtest/replay.py's run_backtest exactly (same "one
trade at a time", same stop/target_1 resolution) so this produces the
identical entry list a real run_backtest.py pass would -- exit-rule
sweeping then asks "what if this same, already-decided entry had used a
different stop/target", not "what if the system entered differently",
which is the only question a parameter sweep can answer without becoming
a different, overfit-prone exercise (re-deciding entries per parameter set
multiplies both the compute cost and the overfitting risk).

Usage:
    python3 capture_entries.py <instrument> <daily_profiles.csv> <intraday_history.csv> <out_dir>
"""
from __future__ import annotations

import array
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from trading_system.bridge.csv_bridge import read_daily_profiles, read_live_state_history
from trading_system.composite.engine import CompositeEngine
from trading_system.engine import LiveEngine
from trading_system.run_live import INSTRUMENT_CONFIGS, resolve_fixed_risk_distance


def _nearest_composite_context(composites, price: float):
    """has_composite, day_count, dist_to_val, dist_to_vah, position_in_range
    (0=at VAL, 1=at VAH, clamped) for the composite whose [val,vah] is
    closest to ``price`` -- the "fading -2SD/+2SD of an established
    composite" pattern the user described needs to know where price sits
    *within* a composite's range, not just whether one exists.
    """
    if not composites:
        return (0, 0, 0.0, 0.0, 0.5)
    best = min(composites, key=lambda c: min(abs(price - c.val), abs(price - c.vah)) if not (c.val <= price <= c.vah) else 0.0)
    dist_val = price - best.val
    dist_vah = best.vah - price
    height = best.vah - best.val
    position = (price - best.val) / height if height > 0 else 0.5
    position = max(0.0, min(1.0, position))
    return (1, best.day_count, dist_val, dist_vah, position)


def main() -> None:
    instrument, daily_path, intraday_path, out_dir = sys.argv[1:5]
    if instrument not in INSTRUMENT_CONFIGS:
        raise ValueError(f"No InstrumentConfig for {instrument!r}")
    live_config = INSTRUMENT_CONFIGS[instrument]

    daily_profiles = sorted(
        (p for p in read_daily_profiles(Path(daily_path)) if p.instrument == instrument),
        key=lambda p: p.session_date,
    )
    states = sorted(
        (s for s in read_live_state_history(Path(intraday_path)) if s.instrument == instrument),
        key=lambda s: s.timestamp,
    )
    print(f"{len(states):,} states, {len(daily_profiles):,} daily profiles", file=sys.stderr)

    prices = array.array("d", (s.last_price for s in states))
    with open(f"{out_dir}/prices.bin", "wb") as f:
        prices.tofile(f)

    composite_engine = CompositeEngine()
    engine = LiveEngine(
        instrument,
        session_flush_threshold=live_config.session_flush_threshold,
        session_reset_retracement_threshold=live_config.session_reset_retracement_threshold,
        session_renewal_threshold=live_config.session_renewal_threshold,
    )

    fieldnames = [
        "trade_id", "entry_index", "timestamp", "day_of_week", "hour",
        "direction", "hypothesis_type", "confluence",
        "entry_price", "stop_price", "target_1_price", "target_2_price", "runner_price",
        "structural_risk", "regime",
        "htf_direction", "htf_conviction", "monthly_extension",
        "has_composite", "composite_day_count", "dist_to_composite_val", "dist_to_composite_vah",
        "position_in_composite",
        "actual_outcome", "actual_r_multiple",
    ]
    out_f = open(f"{out_dir}/entries.csv", "w", newline="")
    writer = csv.DictWriter(out_f, fieldnames=fieldnames)
    writer.writeheader()

    profile_idx = 0
    open_trade = None  # dict of pending entry info + row, filled in once resolved
    trade_id = 0
    n_classified = 0

    for i, state in enumerate(states):
        while profile_idx < len(daily_profiles) and daily_profiles[profile_idx].session_date < state.timestamp.date():
            composite_engine.ingest_day(daily_profiles[profile_idx])
            profile_idx += 1

        if open_trade is not None:
            price = state.last_price
            direction = open_trade["direction"]
            stop = open_trade["row"]["stop_price"]
            target = open_trade["row"]["target_1_price"]
            stop_hit = price <= stop if direction == "long" else price >= stop
            target_hit = (price >= target) if direction == "long" else (price <= target)
            if stop_hit or target_hit:
                risk = open_trade["row"]["structural_risk"]
                if stop_hit:
                    open_trade["row"]["actual_outcome"] = "loss"
                    open_trade["row"]["actual_r_multiple"] = -1.0
                else:
                    open_trade["row"]["actual_outcome"] = "win"
                    open_trade["row"]["actual_r_multiple"] = (
                        abs(target - open_trade["row"]["entry_price"]) / risk if risk > 0 else None
                    )
                writer.writerow(open_trade["row"])
                open_trade = None
            continue

        fixed_risk_distance = (
            state.vwap_intraday_sd1
            if live_config.use_vwap_sd1_as_risk_distance and state.vwap_intraday_sd1 > 0
            else resolve_fixed_risk_distance(live_config)
        )
        result = engine.tick(
            state, composite_engine.composites, live_config.sizing,
            live_config.price_move_threshold, live_config.delta_move_threshold,
            live_config.delta_imbalance, live_config.rrr, fixed_risk_distance,
        )
        n_classified += 1
        if result.proposal is None or result.hypothesis is None or result.hypothesis.target_1 is None:
            continue

        hyp = result.hypothesis
        has_c, c_days, dist_val, dist_vah, pos = _nearest_composite_context(composite_engine.composites, state.last_price)
        trade_id += 1
        row = {
            "trade_id": trade_id,
            "entry_index": i,
            "timestamp": state.timestamp.isoformat(),
            "day_of_week": state.timestamp.weekday(),
            "hour": state.timestamp.hour,
            "direction": result.proposal.direction,
            "hypothesis_type": hyp.type.value,
            "confluence": hyp.confluence.value,
            "entry_price": hyp.entry,
            "stop_price": hyp.invalidation,
            "target_1_price": hyp.target_1,
            "target_2_price": hyp.target_2,
            "runner_price": hyp.runner,
            "structural_risk": abs(hyp.entry - hyp.invalidation),
            "regime": result.regime.value,
            "htf_direction": result.htf_bias.direction.value,
            "htf_conviction": result.htf_bias.conviction.value,
            "monthly_extension": result.htf_bias.monthly_extension,
            "has_composite": has_c,
            "composite_day_count": c_days,
            "dist_to_composite_val": dist_val,
            "dist_to_composite_vah": dist_vah,
            "position_in_composite": pos,
            "actual_outcome": "open",
            "actual_r_multiple": None,
        }
        open_trade = {"direction": result.proposal.direction, "row": row}

        if trade_id % 5000 == 0:
            print(f"  ...{trade_id:,} trades, {n_classified:,} ticks classified, state {i:,}/{len(states):,}", file=sys.stderr)

    if open_trade is not None:
        writer.writerow(open_trade["row"])  # still "open" -- never resolved before data ran out

    out_f.close()
    print(f"Done: {trade_id:,} trades captured, {n_classified:,} ticks classified.", file=sys.stderr)


if __name__ == "__main__":
    main()
