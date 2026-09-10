from datetime import date, datetime

import pytest

from trading_system.bridge.csv_bridge import LiveMarketState, read_composites, read_hypothesis, write_daily_profiles, write_live_state
from trading_system.composite.engine import CompositeEngine
from trading_system.composite.models import DailyProfile
from trading_system.engine import LiveEngine
from trading_system.run_live import INSTRUMENT_CONFIGS, _tick, run


def test_tick_writes_hypothesis_end_to_end(tmp_path):
    instrument_dir = tmp_path / "NQ"
    instrument_dir.mkdir()
    daily_profile_path = instrument_dir / "daily_profile_export.csv"
    live_state_path = instrument_dir / "live_state.csv"
    composites_path = instrument_dir / "composites.csv"
    hypothesis_path = instrument_dir / "hypothesis.txt"

    write_daily_profiles(
        daily_profile_path,
        [DailyProfile("NQ", date(2026, 9, 9), val=100.0, vah=110.0, poc=105.0)],
    )
    state = LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=102.0,
        session_open=105.0,
        vwap_monthly=95.0,
        vwap_weekly=110.0,
        vwap_intraday=100.0,
        cum_delta=50.0,
    )
    write_live_state(live_state_path, state)

    composite_engine = CompositeEngine()
    engine = LiveEngine("NQ")
    _tick(
        engine,
        composite_engine,
        set(),
        INSTRUMENT_CONFIGS["NQ"],
        live_state_path,
        daily_profile_path,
        composites_path,
        hypothesis_path,
    )

    instrument, generated_at, body = read_hypothesis(hypothesis_path)
    assert instrument == "NQ"
    assert generated_at == state.timestamp
    assert "A short" in body

    # composites.csv is written (empty here -- a single day can't form a
    # 2-day composite yet) so ACSIL's composite-zone reader never trips on
    # a missing file once this process is running.
    assert composites_path.exists()
    assert read_composites(composites_path) == []


def test_tick_is_a_noop_when_live_state_missing(tmp_path):
    instrument_dir = tmp_path / "NQ"
    instrument_dir.mkdir()
    composite_engine = CompositeEngine()
    engine = LiveEngine("NQ")

    # No live_state.csv written at all -- should return quietly, not raise.
    _tick(
        engine,
        composite_engine,
        set(),
        INSTRUMENT_CONFIGS["NQ"],
        instrument_dir / "live_state.csv",
        instrument_dir / "daily_profile_export.csv",
        instrument_dir / "composites.csv",
        instrument_dir / "hypothesis.txt",
    )
    assert not (instrument_dir / "hypothesis.txt").exists()


def test_run_raises_a_clear_error_for_an_unconfigured_instrument(tmp_path):
    with pytest.raises(ValueError, match="ES"):
        run(tmp_path, "ES")
