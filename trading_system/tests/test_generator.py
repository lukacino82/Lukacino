from datetime import date, datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.composite.models import Composite
from trading_system.hypothesis.delta import DeltaSignal
from trading_system.hypothesis.generator import (
    Confluence,
    HypothesisType,
    generate_hypothesis,
)
from trading_system.hypothesis.regime import Regime
from trading_system.hypothesis.tiers import Position, StructuralBias, TierReport


def _state(price: float, session_open: float = 100.0, intraday: float = 100.0) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=price,
        session_open=session_open,
        vwap_monthly=100.0,
        vwap_weekly=100.0,
        vwap_intraday=intraday,
        cum_delta=0.0,
    )


def _composite(val: float, vah: float, day_count: int = 3) -> Composite:
    return Composite(
        instrument="NQ",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 5),
        val=val,
        vah=vah,
        day_count=day_count,
    )


_A_DAY_NEUTRAL_TIERS_BELOW = TierReport(monthly=Position.ABOVE, weekly=Position.BELOW, intraday=Position.BELOW)
_A_DAY_NEUTRAL_TIERS_ABOVE = TierReport(monthly=Position.ABOVE, weekly=Position.BELOW, intraday=Position.ABOVE)
_A_DAY_AT_MEAN_TIERS = TierReport(monthly=Position.ABOVE, weekly=Position.BELOW, intraday=Position.AT)
_B_DAY_BULLISH_TIERS = TierReport(monthly=Position.ABOVE, weekly=Position.ABOVE, intraday=Position.ABOVE)
_B_DAY_BEARISH_TIERS = TierReport(monthly=Position.BELOW, weekly=Position.BELOW, intraday=Position.BELOW)


def test_unclear_regime_produces_no_hypothesis():
    state = _state(price=100.0)
    result = generate_hypothesis(state, Regime.UNCLEAR, _A_DAY_NEUTRAL_TIERS_BELOW, DeltaSignal.NEUTRAL)
    assert result is None


def test_a_day_long_when_price_below_intraday_vwap():
    state = _state(price=95.0, intraday=100.0)
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_NEUTRAL_TIERS_BELOW, DeltaSignal.NEUTRAL)
    assert result is not None
    assert result.type == HypothesisType.A_LONG
    assert result.entry == 95.0


def test_a_day_short_when_price_above_intraday_vwap():
    state = _state(price=105.0, intraday=100.0)
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_NEUTRAL_TIERS_ABOVE, DeltaSignal.NEUTRAL)
    assert result is not None
    assert result.type == HypothesisType.A_SHORT


def test_a_day_no_hypothesis_when_price_at_intraday_vwap():
    state = _state(price=100.0, intraday=100.0)
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_AT_MEAN_TIERS, DeltaSignal.NEUTRAL)
    assert result is None


def test_a_day_target_falls_back_to_intraday_vwap_with_no_composites():
    state = _state(price=95.0, intraday=100.0)
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_NEUTRAL_TIERS_BELOW, DeltaSignal.NEUTRAL)
    assert result.target_1 == 100.0
    assert result.target_2 is None
    assert result.runner is None


def test_a_day_uses_nearest_composite_as_target_and_defends_invalidation():
    state = _state(price=95.0, intraday=100.0, session_open=90.0)
    composites = [
        _composite(val=98.0, vah=99.0, day_count=2),  # nearest target above price
        _composite(val=102.0, vah=104.0, day_count=5),  # stronger, further target
        _composite(val=85.0, vah=88.0, day_count=4),  # below price -> invalidation side
    ]
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_NEUTRAL_TIERS_BELOW, DeltaSignal.NEUTRAL, composites)
    assert result.target_1 == 98.0
    assert result.target_2 == 102.0
    assert result.runner == 102.0  # highest day_count among targets above price
    assert result.invalidation == 88.0  # nearest composite edge below price


def test_a_day_confluence_a_plus_with_supporting_delta_and_target():
    state = _state(price=95.0, intraday=100.0)
    composites = [_composite(val=98.0, vah=99.0, day_count=3)]
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_NEUTRAL_TIERS_BELOW, DeltaSignal.DIVERGENCE, composites)
    assert result.confluence == Confluence.A_PLUS
    assert result.is_primary


def test_a_day_confluence_weak_when_delta_confirms_the_move_away_from_mean():
    state = _state(price=95.0, intraday=100.0)
    result = generate_hypothesis(state, Regime.A_DAY, _A_DAY_NEUTRAL_TIERS_BELOW, DeltaSignal.CONFIRMING)
    assert result.confluence == Confluence.WEAK
    assert not result.is_primary


def test_b_day_long_when_bullish_bias():
    state = _state(price=110.0)
    result = generate_hypothesis(state, Regime.B_DAY, _B_DAY_BULLISH_TIERS, DeltaSignal.CONFIRMING)
    assert result.type == HypothesisType.B_LONG


def test_b_day_short_when_bearish_bias():
    state = _state(price=90.0)
    result = generate_hypothesis(state, Regime.B_DAY, _B_DAY_BEARISH_TIERS, DeltaSignal.CONFIRMING)
    assert result.type == HypothesisType.B_SHORT


def test_b_day_target_is_none_without_a_composite_in_trend_direction():
    state = _state(price=110.0)
    result = generate_hypothesis(state, Regime.B_DAY, _B_DAY_BULLISH_TIERS, DeltaSignal.CONFIRMING)
    assert result.target_1 is None
    assert result.invalidation == state.vwap_intraday


def test_b_day_confluence_a_plus_with_confirming_delta_and_target():
    state = _state(price=110.0)
    composites = [_composite(val=115.0, vah=118.0, day_count=4)]
    result = generate_hypothesis(state, Regime.B_DAY, _B_DAY_BULLISH_TIERS, DeltaSignal.CONFIRMING, composites)
    assert result.confluence == Confluence.A_PLUS


def test_b_day_confluence_weak_when_delta_diverges_from_the_breakout():
    state = _state(price=110.0)
    result = generate_hypothesis(state, Regime.B_DAY, _B_DAY_BULLISH_TIERS, DeltaSignal.DIVERGENCE)
    assert result.confluence == Confluence.WEAK
