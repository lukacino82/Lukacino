"""Polls one instrument's bridge files and keeps hypothesis.txt / composites.csv
up to date for ACSIL to draw.

Run as a long-lived process alongside Sierra Chart, e.g.:
    python -m trading_system.run_live --bridge-dir "C:\\SierraChart\\TradingHypothesisBridge" --instrument NQ

Every threshold below is instrument-specific -- price/delta magnitudes on
NQ mean nothing on Gold or EURUSD, and NQ's tick_size/tick_value are wrong
for any other contract. There is no sane fallback, so an instrument with no
entry in INSTRUMENT_CONFIGS fails loudly at startup instead of silently
running with another instrument's numbers. Add an entry before running this
for a new instrument. All values here are placeholders, not calibrated
(see ARCHITECTURE.md / hypothesis/regime.py), except NQ's tick_size/
tick_value, which are its real CME contract specs.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from .bridge.csv_bridge import (
    LiveMarketState,
    OrderProposalSnapshot,
    append_live_state,
    read_daily_profiles,
    read_live_state,
    read_live_state_history,
    write_composites,
    write_hypothesis,
    write_order_proposal,
)
from .composite.engine import CompositeEngine
from .engine import LiveEngine
from .risk.sizing import SizingConfig, SizingMode


@dataclass(frozen=True)
class InstrumentConfig:
    sizing: SizingConfig
    price_move_threshold: float
    delta_move_threshold: float
    delta_imbalance: float
    # Optional fixed reward:risk override for target_1, e.g. 1.5 for a
    # 1.5:1 RRR -- None (the default) keeps target_1 structural (nearest
    # composite/POC level, or the existing VWAP fallback), matching
    # behavior before this existed. See hypothesis/generator.py's module
    # docstring for exactly what this changes and what it leaves alone
    # (target_2 and runner are never RRR-derived). Applies to both Semi
    # Auto and Fully Auto identically -- it's applied here in Python,
    # before anything reaches order_proposal.csv.
    rrr: Optional[float] = None
    # Optional fixed stop-loss distance, replacing the structural
    # (composite/VWAP-derived) invalidation entirely when set -- added
    # after a real Replay-mode run picked an ancient composite edge
    # thousands of points from price as the stop (nothing ever invalidates
    # a composite just because price ran away from it, only a newer
    # composite overlapping it -- see hypothesis/generator.py's module
    # docstring). Set exactly one of these two, not both:
    #   fixed_risk_points -- distance in this instrument's own price units
    #     (e.g. 50.0 = 50 NQ points).
    #   fixed_risk_usd -- distance expressed as the dollar risk *per
    #     contract* it should work out to; converted to a price distance
    #     via sizing.tick_size/tick_value (see resolve_fixed_risk_distance
    #     below). Only meaningful when sizing.tick_size/tick_value are set.
    # Leaving both None (the default) keeps the original structural-stop
    # behavior. Applies to both Semi Auto and Fully Auto, same as rrr.
    fixed_risk_points: Optional[float] = None
    fixed_risk_usd: Optional[float] = None
    # When True, prefer the live, per-tick distance from LiveMarketState.
    # vwap_intraday_sd1 (ACSIL's intraday VWAP study's own +1 standard
    # deviation band, exported fresh every tick) over the static
    # fixed_risk_points/fixed_risk_usd above -- added at the user's
    # request to use "1 SD of the VWAP envelope" as the stop distance
    # instead of one fixed number, since that band's width itself changes
    # with the session's actual volatility. Falls back to
    # fixed_risk_points/fixed_risk_usd (see resolve_effective_fixed_risk_
    # distance) whenever vwap_intraday_sd1 isn't available yet (0.0 --
    # e.g. ACSIL hasn't been rebuilt with the new subgraph input, or the
    # VWAP study hasn't accumulated enough of the session to compute a
    # band), so a trade is never sized off a plain zero distance.
    use_vwap_sd1_as_risk_distance: bool = False


def resolve_fixed_risk_distance(config: "InstrumentConfig") -> Optional[float]:
    """Converts InstrumentConfig's fixed_risk_points/fixed_risk_usd (at most
    one set) into the single price-distance float generator.py needs --
    kept here rather than in generator.py since it's the only place that
    knows this instrument's tick_size/tick_value are for converting units,
    not for anything about the hypothesis itself.
    """
    if config.fixed_risk_points is not None and config.fixed_risk_usd is not None:
        raise ValueError("Set only one of fixed_risk_points/fixed_risk_usd, not both.")
    if config.fixed_risk_points is not None:
        return config.fixed_risk_points
    if config.fixed_risk_usd is not None:
        if config.sizing.tick_size <= 0 or config.sizing.tick_value <= 0:
            raise ValueError("fixed_risk_usd needs sizing.tick_size/tick_value to convert to a price distance.")
        return config.fixed_risk_usd / config.sizing.tick_value * config.sizing.tick_size
    return None


def resolve_effective_fixed_risk_distance(config: "InstrumentConfig", state: LiveMarketState) -> Optional[float]:
    """The distance actually used for this tick: state.vwap_intraday_sd1
    when use_vwap_sd1_as_risk_distance is on and ACSIL actually supplied
    one (> 0), else whatever resolve_fixed_risk_distance's static config
    gives (which is itself None when neither fixed_risk_points/usd is set,
    keeping the original structural-stop behavior).
    """
    if config.use_vwap_sd1_as_risk_distance and state.vwap_intraday_sd1 > 0:
        return state.vwap_intraday_sd1
    return resolve_fixed_risk_distance(config)


INSTRUMENT_CONFIGS: Dict[str, InstrumentConfig] = {
    "NQ": InstrumentConfig(
        # FIXED_RISK_USD + fixed_risk_points below (instead of the previous
        # FIXED_CONTRACTS/no-fixed-stop setup) at the user's request, so
        # contracts scale off a real dollar-risk budget instead of a flat
        # count, and the stop can never again land on an ancient,
        # price-irrelevant composite edge the way it did in a real Replay
        # run (see hypothesis/generator.py's module docstring). NQ's
        # tick_size/tick_value are its real CME contract specs; every dollar
        # figure below (full/half_risk_usd, fixed_risk_points) is a
        # PLACEHOLDER -- replace with your actual per-trade risk tolerance
        # before trusting this live. As configured: a fixed 25-point stop
        # ($500/contract, since 25/0.25*5=500) with a $1000 budget on A+
        # (-> 2 contracts) and $500 on clean (-> 1 contract) -- the same
        # 2/1 split the old FIXED_CONTRACTS numbers gave, just now risk-
        # budget-driven instead of a flat count.
        sizing=SizingConfig(
            mode=SizingMode.FIXED_RISK_USD,
            full_risk_usd=1000.0,
            half_risk_usd=500.0,
            tick_size=0.25,
            tick_value=5.0,
        ),
        price_move_threshold=5.0,  # NQ points -- placeholder, not calibrated
        delta_move_threshold=500.0,  # placeholder, not calibrated
        # Bumped from the original 1000.0 placeholder after a real
        # --history-out sample (2026-09-15, 19:17-19:24 ET) showed NQ's
        # cum_delta already sitting at 4600-4800 within that single 7-minute
        # window -- 1000 would have made "balanced_delta" (required for
        # A_DAY) essentially never true, and the backtest's regime_counts
        # diagnostic confirmed 100% UNCLEAR against that data. 5000 isn't a
        # calibrated number either (still needs a real distribution across
        # many days, ideally by time-of-day since cum_delta only grows
        # through the session) -- it's a less-obviously-wrong placeholder so
        # near-term backtests have a chance to see A_DAY at all while more
        # history accumulates.
        delta_imbalance=5000.0,
        rrr=1.5,
        fixed_risk_points=25.0,  # PLACEHOLDER fallback -- see use_vwap_sd1_as_risk_distance below
        # Prefer the live 1-SD VWAP envelope width over the flat 25-point
        # fallback above, per the user's request -- requires ACSIL to be
        # rebuilt with the new "VWAP Intraday +1 SD Band" input (Study
        # Settings: DAY-VWAP, ID:5 in the user's real chart -- Top Band 2 /
        # SG4, since that study's Band 2 Std Deviation Multiplier is 1.0,
        # i.e. the actual +1 SD band, NOT Band 1 whose multiplier is 0.5).
        # Falls back to fixed_risk_points automatically (see
        # resolve_effective_fixed_risk_distance) whenever live_state.csv's
        # vwap_intraday_sd1 is still 0.0 -- e.g. before that ACSIL rebuild
        # is deployed.
        use_vwap_sd1_as_risk_distance=True,
    ),
}

POLL_INTERVAL_SECONDS = 5


def _append_new_history_row(history_path: Optional[Path], state) -> None:
    """No-op unless ``--history-out`` was passed. Dedupes on timestamp so
    polling faster than ACSIL's own refresh interval doesn't write the same
    snapshot twice -- this is the historical_intraday.csv the backtest
    harness (trading_system/backtest/replay.py) reads via
    read_live_state_history, so duplicate rows would double-count that tick.
    Re-reads the whole file each call to find the last row -- fine at 5s
    polling, would need revisiting for a very long-running history file.
    """
    if history_path is None:
        return
    if history_path.exists():
        existing = read_live_state_history(history_path)
        if existing and existing[-1].timestamp == state.timestamp:
            return  # ACSIL hasn't refreshed since the last poll -- same snapshot
    append_live_state(history_path, state)


def _order_proposal_snapshot(state, result) -> OrderProposalSnapshot:
    """Always returns a row -- direction="none"/contracts=0 when
    ``result.proposal`` is None, so ACSIL can tell "checked, nothing
    tradeable right now" apart from a missing/stale file. See
    OrderProposalSnapshot's docstring for why this shape exists at all
    (Step 4: a machine-readable counterpart to hypothesis.txt's free text).
    """
    proposal = result.proposal
    if proposal is None:
        return OrderProposalSnapshot(
            timestamp=state.timestamp,
            instrument=state.instrument,
            direction="none",
            hypothesis_type="",
            confluence="",
            entry=None,
            stop=None,
            target_1=None,
            target_2=None,
            runner=None,
            contracts=0,
            contracts_target1=0,
            contracts_target2=0,
            contracts_runner=0,
        )
    return OrderProposalSnapshot(
        timestamp=state.timestamp,
        instrument=proposal.instrument,
        direction=proposal.direction,
        hypothesis_type=proposal.hypothesis_type.value,
        confluence=proposal.confluence.value,
        entry=proposal.entry,
        stop=proposal.stop,
        target_1=proposal.target_1,
        target_2=proposal.target_2,
        runner=proposal.runner,
        contracts=proposal.contracts,
        contracts_target1=proposal.contracts_target1,
        contracts_target2=proposal.contracts_target2,
        contracts_runner=proposal.contracts_runner,
    )


def _tick(
    engine: LiveEngine,
    composite_engine: CompositeEngine,
    ingested_dates: Set,
    config: InstrumentConfig,
    live_state_path: Path,
    daily_profile_path: Path,
    composites_path: Path,
    hypothesis_path: Path,
    history_path: Optional[Path] = None,
    order_proposal_path: Optional[Path] = None,
) -> None:
    if not live_state_path.exists():
        return  # ACSIL hasn't written a snapshot yet
    state = read_live_state(live_state_path)
    if state is None:
        return  # header written but no data row yet
    _append_new_history_row(history_path, state)

    if daily_profile_path.exists():
        for profile in read_daily_profiles(daily_profile_path):
            if profile.session_date not in ingested_dates:
                composite_engine.ingest_day(profile)
                ingested_dates.add(profile.session_date)
        write_composites(composites_path, composite_engine.composites)

    result = engine.tick(
        state,
        composite_engine.composites,
        config.sizing,
        config.price_move_threshold,
        config.delta_move_threshold,
        config.delta_imbalance,
        config.rrr,
        resolve_effective_fixed_risk_distance(config, state),
    )
    write_hypothesis(hypothesis_path, instrument=state.instrument, generated_at=state.timestamp, body=result.hypothesis_text)
    if order_proposal_path is not None:
        write_order_proposal(order_proposal_path, _order_proposal_snapshot(state, result))


def run(
    bridge_dir: Path,
    instrument: str,
    history_path: Optional[Path] = None,
    order_proposal_path: Optional[Path] = None,
) -> None:
    if instrument not in INSTRUMENT_CONFIGS:
        known = ", ".join(sorted(INSTRUMENT_CONFIGS)) or "(none configured)"
        raise ValueError(
            f"No InstrumentConfig for {instrument!r} in run_live.py's INSTRUMENT_CONFIGS "
            f"(configured: {known}). Add one with this instrument's real tick_size/"
            f"tick_value before running -- reusing another instrument's numbers would "
            f"silently size positions wrong."
        )
    config = INSTRUMENT_CONFIGS[instrument]

    instrument_dir = bridge_dir / instrument
    live_state_path = instrument_dir / "live_state.csv"
    daily_profile_path = instrument_dir / "daily_profile_export.csv"
    composites_path = instrument_dir / "composites.csv"
    hypothesis_path = instrument_dir / "hypothesis.txt"
    # Written every tick by default (unlike --history-out, which is opt-in) --
    # this is the Step 4 order-automation bridge file, so ACSIL should always
    # have a current one to read once its manual-trigger side is built.
    if order_proposal_path is None:
        order_proposal_path = instrument_dir / "order_proposal.csv"

    composite_engine = CompositeEngine()
    ingested_dates: Set = set()
    engine = LiveEngine(instrument)

    print(f"Watching {instrument_dir} (poll every {POLL_INTERVAL_SECONDS}s) ...")
    while True:
        try:
            _tick(
                engine,
                composite_engine,
                ingested_dates,
                config,
                live_state_path,
                daily_profile_path,
                composites_path,
                hypothesis_path,
                history_path,
                order_proposal_path,
            )
        except FileNotFoundError:
            pass  # ACSIL hasn't created the bridge folder yet
        except Exception as exc:  # keep the loop alive on a bad row/parse error
            print(f"tick failed: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-dir", required=True)
    parser.add_argument("--instrument", required=True)
    parser.add_argument(
        "--history-out",
        type=Path,
        default=None,
        help=(
            "Optional path to append every new live_state.csv snapshot to, building up "
            "real intraday history for trading_system/run_backtest.py / threshold "
            "calibration over time. Omit to run exactly as before (no history logging)."
        ),
    )
    parser.add_argument(
        "--order-proposal-out",
        type=Path,
        default=None,
        help=(
            "Optional override for order_proposal.csv's path (defaults to "
            "<bridge-dir>/<instrument>/order_proposal.csv, written every tick). "
            "This is the machine-readable file ACSIL reads to place orders "
            "(Step 4: manual trigger first, auto mode later) -- see ARCHITECTURE.md."
        ),
    )
    args = parser.parse_args()
    run(Path(args.bridge_dir), args.instrument, args.history_out, args.order_proposal_out)
