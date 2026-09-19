from datetime import date, datetime

import pytest

from trading_system.bridge.csv_bridge import (
    LiveMarketState,
    read_composites,
    read_hypothesis,
    read_live_state_history,
    read_order_proposal,
    write_daily_profiles,
    write_live_state,
)
from trading_system.composite.engine import CompositeEngine
from trading_system.composite.models import DailyProfile
from trading_system.engine import LiveEngine
from trading_system.risk.sizing import SizingConfig, SizingMode
from trading_system.run_live import (
    INSTRUMENT_CONFIGS,
    InstrumentConfig,
    _tick,
    resolve_effective_fixed_risk_distance,
    resolve_fixed_risk_distance,
    run,
)


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


def test_tick_appends_to_history_and_dedupes_unchanged_snapshots(tmp_path):
    instrument_dir = tmp_path / "NQ"
    instrument_dir.mkdir()
    live_state_path = instrument_dir / "live_state.csv"
    history_path = instrument_dir / "historical_intraday.csv"

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

    # Two polls before ACSIL has refreshed live_state.csv again -- must not
    # write the same snapshot to history twice (see _append_new_history_row).
    for _ in range(2):
        _tick(
            engine,
            composite_engine,
            set(),
            INSTRUMENT_CONFIGS["NQ"],
            live_state_path,
            instrument_dir / "daily_profile_export.csv",
            instrument_dir / "composites.csv",
            instrument_dir / "hypothesis.txt",
            history_path,
        )
    assert read_live_state_history(history_path) == [state]

    # A genuine new refresh (later timestamp) must append a second row.
    later_state = LiveMarketState(**{**state.__dict__, "timestamp": datetime(2026, 9, 10, 14, 0, 5)})
    write_live_state(live_state_path, later_state)
    _tick(
        engine,
        composite_engine,
        set(),
        INSTRUMENT_CONFIGS["NQ"],
        live_state_path,
        instrument_dir / "daily_profile_export.csv",
        instrument_dir / "composites.csv",
        instrument_dir / "hypothesis.txt",
        history_path,
    )
    assert read_live_state_history(history_path) == [state, later_state]


def test_tick_writes_order_proposal_when_path_given(tmp_path):
    instrument_dir = tmp_path / "NQ"
    instrument_dir.mkdir()
    daily_profile_path = instrument_dir / "daily_profile_export.csv"
    live_state_path = instrument_dir / "live_state.csv"
    order_proposal_path = instrument_dir / "order_proposal.csv"

    write_daily_profiles(
        daily_profile_path,
        [DailyProfile("NQ", date(2026, 9, 9), val=100.0, vah=110.0, poc=105.0)],
    )
    # Same setup as test_tick_writes_hypothesis_end_to_end -- known to
    # produce an actionable A-short hypothesis.
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
        instrument_dir / "composites.csv",
        instrument_dir / "hypothesis.txt",
        None,
        order_proposal_path,
    )

    proposal = read_order_proposal(order_proposal_path)
    assert proposal is not None
    assert proposal.timestamp == state.timestamp
    assert proposal.direction == "short"
    assert proposal.contracts > 0


def test_tick_writes_none_order_proposal_when_regime_unclear(tmp_path):
    instrument_dir = tmp_path / "NQ"
    instrument_dir.mkdir()
    live_state_path = instrument_dir / "live_state.csv"
    order_proposal_path = instrument_dir / "order_proposal.csv"

    # No daily_profile_export.csv / composites -- yesterday is None, which
    # LiveEngine treats as an unclear regime, so no hypothesis/proposal.
    state = LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=100.0,
        session_open=100.0,
        vwap_monthly=100.0,
        vwap_weekly=100.0,
        vwap_intraday=100.0,
        cum_delta=0.0,
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
        instrument_dir / "daily_profile_export.csv",
        instrument_dir / "composites.csv",
        instrument_dir / "hypothesis.txt",
        None,
        order_proposal_path,
    )

    proposal = read_order_proposal(order_proposal_path)
    assert proposal is not None
    assert proposal.direction == "none"
    assert proposal.contracts == 0


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


def _config(
    fixed_risk_points=None, fixed_risk_usd=None, tick_size=0.0, tick_value=0.0, use_vwap_sd1_as_risk_distance=False,
) -> InstrumentConfig:
    return InstrumentConfig(
        sizing=SizingConfig(mode=SizingMode.FIXED_CONTRACTS, tick_size=tick_size, tick_value=tick_value),
        price_move_threshold=5.0,
        delta_move_threshold=500.0,
        delta_imbalance=1000.0,
        fixed_risk_points=fixed_risk_points,
        fixed_risk_usd=fixed_risk_usd,
        use_vwap_sd1_as_risk_distance=use_vwap_sd1_as_risk_distance,
    )


def _state_with_sd1(vwap_intraday_sd1: float) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=100.0,
        session_open=100.0,
        vwap_monthly=100.0,
        vwap_weekly=100.0,
        vwap_intraday=100.0,
        cum_delta=0.0,
        vwap_intraday_sd1=vwap_intraday_sd1,
    )


def test_resolve_fixed_risk_distance_is_none_when_neither_is_set():
    assert resolve_fixed_risk_distance(_config()) is None


def test_resolve_fixed_risk_distance_returns_points_directly():
    assert resolve_fixed_risk_distance(_config(fixed_risk_points=25.0)) == 25.0


def test_resolve_fixed_risk_distance_converts_usd_via_tick_size_and_value():
    # NQ-like specs: tick_size=0.25, tick_value=5.0 -> $20/point.
    # $500 / $20 = 25 points.
    config = _config(fixed_risk_usd=500.0, tick_size=0.25, tick_value=5.0)
    assert resolve_fixed_risk_distance(config) == 25.0


def test_resolve_fixed_risk_distance_raises_when_both_are_set():
    with pytest.raises(ValueError, match="only one"):
        resolve_fixed_risk_distance(_config(fixed_risk_points=25.0, fixed_risk_usd=500.0))


def test_resolve_fixed_risk_distance_raises_when_usd_set_without_tick_specs():
    with pytest.raises(ValueError, match="tick_size/tick_value"):
        resolve_fixed_risk_distance(_config(fixed_risk_usd=500.0))


def test_resolve_effective_prefers_live_sd1_when_enabled_and_present():
    config = _config(fixed_risk_points=25.0, use_vwap_sd1_as_risk_distance=True)
    assert resolve_effective_fixed_risk_distance(config, _state_with_sd1(12.5)) == 12.5


def test_resolve_effective_falls_back_to_static_when_sd1_is_zero():
    # ACSIL not yet supplying a real value (e.g. before the rebuild that
    # adds the SD-band input, or too early in the session) -- must not
    # size/stop off a literal 0.0 distance.
    config = _config(fixed_risk_points=25.0, use_vwap_sd1_as_risk_distance=True)
    assert resolve_effective_fixed_risk_distance(config, _state_with_sd1(0.0)) == 25.0


def test_resolve_effective_ignores_sd1_when_flag_is_off():
    config = _config(fixed_risk_points=25.0, use_vwap_sd1_as_risk_distance=False)
    assert resolve_effective_fixed_risk_distance(config, _state_with_sd1(12.5)) == 25.0


def test_resolve_effective_is_none_when_nothing_is_configured():
    assert resolve_effective_fixed_risk_distance(_config(), _state_with_sd1(0.0)) is None
