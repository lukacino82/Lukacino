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


INSTRUMENT_CONFIGS: Dict[str, InstrumentConfig] = {
    "NQ": InstrumentConfig(
        sizing=SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1),
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
