from datetime import datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.engine import NO_HYPOTHESIS_TEXT, LiveEngine
from trading_system.hypothesis.delta import DeltaSignal
from trading_system.hypothesis.generator import Confluence, HypothesisType
from trading_system.hypothesis.regime import Regime
from trading_system.hypothesis.synthesis import HTFConviction
from trading_system.hypothesis.tiers import StructuralBias
from trading_system.risk.sizing import SizingConfig, SizingMode


def _state(
    last_price: float,
    session_open: float,
    cum_delta: float = 0.0,
    vwap_monthly: float = 95.0,
    vwap_weekly: float = 110.0,
    vwap_intraday: float = 100.0,
) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=last_price,
        session_open=session_open,
        vwap_monthly=vwap_monthly,
        vwap_weekly=vwap_weekly,
        vwap_intraday=vwap_intraday,
        cum_delta=cum_delta,
    )


_SIZING = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)


def test_tick_produces_no_hypothesis_when_bias_and_delta_disagree():
    engine = LiveEngine("NQ")
    # last_price=115 is above all three tiers (95/110/100) -> BULLISH bias,
    # but cum_delta=0 is balanced -- a mixed read, so UNCLEAR.
    state = _state(last_price=115.0, session_open=105.0)
    result = engine.tick(state, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)
    assert result.regime == Regime.UNCLEAR
    assert result.hypothesis is None
    assert result.proposal is None
    assert result.hypothesis_text == NO_HYPOTHESIS_TEXT


def test_tick_resolves_a_day_and_generates_a_short_hypothesis():
    engine = LiveEngine("NQ")
    # last_price=102 is above vwap_intraday=100 -> A_SHORT (reversion down).
    # monthly AT (pinned to last_price so it never sides with either),
    # weekly BELOW (102<110), intraday ABOVE (102>100) -> ABOVE/BELOW both
    # sit at 1 -- no 2-of-3 majority -> NEUTRAL structural bias -> A-day
    # sign (see tiers.py's structural_bias). No daily profile needed any
    # more -- see hypothesis/regime.py.
    state = _state(last_price=102.0, session_open=105.0, cum_delta=50.0, vwap_monthly=102.0)
    result = engine.tick(state, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)

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
    result1 = engine.tick(state1, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)
    assert result1.delta_signal == DeltaSignal.INSUFFICIENT_DATA

    state2 = _state(last_price=108.0, session_open=105.0, cum_delta=500.0)
    result2 = engine.tick(state2, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)
    assert result2.delta_signal == DeltaSignal.CONFIRMING


def _synthesis_state(last_price: float, cum_delta: float) -> LiveMarketState:
    # ARCHITECTURE.md item 8's worked scenario: MM bullish-cooling, HF in
    # rotation, intraday selloff -- see test_synthesis.py for the isolated
    # version of this fixture.
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 20, 15, 0, 0),
        last_price=last_price,
        session_open=29650.0,
        vwap_monthly=29300.0,
        vwap_weekly=29580.0,
        vwap_intraday=29650.0,
        cum_delta=cum_delta,
        vwap_monthly_sd1=29550.0,
    )


def test_tick_resolves_counter_intraday_on_the_users_worked_scenario():
    engine = LiveEngine("NQ")

    state1 = _synthesis_state(last_price=29575.0, cum_delta=-4100.0)
    engine.tick(state1, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0)

    # Price pushed UP (+5) while delta pushed DOWN (-500) -- absorption,
    # exactly the pattern ARCHITECTURE.md item 8 describes as already
    # producing DeltaSignal.DIVERGENCE.
    state2 = _synthesis_state(last_price=29580.0, cum_delta=-4600.0)
    result = engine.tick(
        state2, [], _SIZING, price_move_threshold=1.0, delta_move_threshold=200.0,
        fixed_risk_distance=50.0,
    )

    assert result.delta_signal == DeltaSignal.DIVERGENCE
    assert result.htf_bias.direction == StructuralBias.BULLISH
    assert result.htf_bias.conviction == HTFConviction.MODERATE
    assert result.regime == Regime.COUNTER_INTRADAY
    assert result.hypothesis is not None
    assert result.hypothesis.type == HypothesisType.COUNTER_LONG
    assert "Counter long" in result.hypothesis_text
    assert result.proposal is not None
    assert result.proposal.direction == "long"
