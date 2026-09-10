"""Polls one instrument's bridge files and keeps hypothesis.txt / composites.csv
up to date for ACSIL to draw.

Run as a long-lived process alongside Sierra Chart, e.g.:
    python -m trading_system.run_live --bridge-dir "C:\\SierraChart\\TradingHypothesisBridge" --instrument NQ

The constants below marked "placeholder, not calibrated" are exactly that --
see ARCHITECTURE.md and hypothesis/regime.py. Fill in real values (sizing
especially -- account_equity, risk fractions or fixed contract counts) before
trusting this for anything beyond watching the output.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional, Set

from .bridge.csv_bridge import (
    read_daily_profiles,
    read_live_state,
    write_composites,
    write_hypothesis,
)
from .composite.engine import CompositeEngine
from .composite.models import DailyProfile
from .engine import LiveEngine
from .risk.sizing import SizingConfig, SizingMode

# --- Fill these in before running for real ----------------------------------
SIZING = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
PRICE_MOVE_THRESHOLD = 5.0  # NQ points -- placeholder, not calibrated
DELTA_MOVE_THRESHOLD = 500.0  # placeholder, not calibrated
GAP_THRESHOLD_FRACTION = 0.25  # placeholder, not calibrated
DELTA_IMBALANCE = 1000.0  # placeholder, not calibrated
POLL_INTERVAL_SECONDS = 5
# -----------------------------------------------------------------------------


def _most_recent_profile(daily_profile_path: Path) -> Optional[DailyProfile]:
    profiles = read_daily_profiles(daily_profile_path)
    return max(profiles, key=lambda p: p.session_date) if profiles else None


def _tick(
    engine: LiveEngine,
    composite_engine: CompositeEngine,
    ingested_dates: Set,
    live_state_path: Path,
    daily_profile_path: Path,
    composites_path: Path,
    hypothesis_path: Path,
) -> None:
    if not live_state_path.exists():
        return  # ACSIL hasn't written a snapshot yet
    state = read_live_state(live_state_path)
    if state is None:
        return  # header written but no data row yet

    if daily_profile_path.exists():
        for profile in read_daily_profiles(daily_profile_path):
            if profile.session_date not in ingested_dates:
                composite_engine.ingest_day(profile)
                ingested_dates.add(profile.session_date)
        write_composites(composites_path, composite_engine.composites)

    yesterday = _most_recent_profile(daily_profile_path) if daily_profile_path.exists() else None

    result = engine.tick(
        state,
        yesterday,
        composite_engine.composites,
        SIZING,
        PRICE_MOVE_THRESHOLD,
        DELTA_MOVE_THRESHOLD,
        GAP_THRESHOLD_FRACTION,
        DELTA_IMBALANCE,
    )
    write_hypothesis(hypothesis_path, instrument=state.instrument, generated_at=state.timestamp, body=result.hypothesis_text)


def run(bridge_dir: Path, instrument: str) -> None:
    instrument_dir = bridge_dir / instrument
    live_state_path = instrument_dir / "live_state.csv"
    daily_profile_path = instrument_dir / "daily_profile_export.csv"
    composites_path = instrument_dir / "composites.csv"
    hypothesis_path = instrument_dir / "hypothesis.txt"

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
                live_state_path,
                daily_profile_path,
                composites_path,
                hypothesis_path,
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
    args = parser.parse_args()
    run(Path(args.bridge_dir), args.instrument)
