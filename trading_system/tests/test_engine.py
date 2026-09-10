from datetime import date, datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.composite.models import DailyProfile
from trading_system.engine import NO_HYPOTHESIS_TEXT, LiveEngine
from trading_system.hypothesis.delta import DeltaSignal
from trading_system.hypothesis.generator import Confluence, HypothesisType
from trading_system.hypothesis.regime import Regime
from trading_system.risk.sizing import SizingConfig, SizingMode


def _state(last_price: float, session_open: float, cum_delta: float = 0.0) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=last_price,
        session_open=session_open,
        vwap_monthly=95.0,
        vwap_weekly=110.0,
        vwap_intraday=100.0,
        cum_delta=cum_delta,
    )


_SIZING = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
_YESTERDAY = DailyProfile("NQ", date(2026, 9, 9), val=100.0, vah=110.0, poc=105.0)


def test_tick_without_yesterday_profile_produces_no_hypothesis():
    engine = LiveEngine("NQ")
    state = _state(last_price=102.0, session_open=105.0)
    result = engine.tick(state, None, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)
    assert result.regime == Regime.UNCLEAR
    assert result.hypothesis is None
    assert result.proposal is None
    assert result.hypothesis_text == NO_HYPOTHESIS_TEXT


def test_tick_resolves_a_day_and_generates_a_short_hypothesis():
    engine = LiveEngine("NQ")
    # last_price=102 is above vwap_intraday=100 -> A_SHORT (reversion down).
    # monthly ABOVE / weekly BELOW -> structural bias NEUTRAL -> A-day sign.
    state = _state(last_price=102.0, session_open=105.0, cum_delta=50.0)
    result = engine.tick(state, _YESTERDAY, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)

    assert result.regime == Regime.A_DAY
    assert result.hypothesis is not None
    assert result.hypothesis.type == HypothesisType.A_SHORT
    assert result.delta_signal == DeltaSignal.INSUFFICIENT_DATA  # only one snapshot so far
    assert result.hypothesis.confluence == Confluence.CLEAN
    assert result.proposal is not None
    assert result.proposal.contracts == 1  # half_risk_contracts for CLEAN
    assert "A short" in result.hypothesis_text


def test_delta_history_persists_across_ticks_on_the_same_engine():
    engine = LiveEngine("NQ", delta_window=5)

    state1 = _state(last_price=102.0, session_open=105.0, cum_delta=0.0)
    result1 = engine.tick(state1, _YESTERDAY, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)
    assert result1.delta_signal == DeltaSignal.INSUFFICIENT_DATA

    state2 = _state(last_price=108.0, session_open=105.0, cum_delta=500.0)
    result2 = engine.tick(state2, _YESTERDAY, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)
    assert result2.delta_signal == DeltaSignal.CONFIRMING
