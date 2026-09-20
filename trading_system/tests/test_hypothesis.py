from datetime import datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.hypothesis.delta import (
    DeltaHistory,
    DeltaSample,
    DeltaSignal,
    classify_delta,
)
from trading_system.hypothesis.regime import Regime, RegimeInputs, classify_regime
from trading_system.hypothesis.tiers import (
    Position,
    StructuralBias,
    TierReport,
    classify_position,
    tier_report,
)


def _state(
    price: float,
    monthly: float,
    weekly: float,
    intraday: float,
    cum_delta: float = 0,
    session_open: float = 0,
) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 9, 0, 0),
        last_price=price,
        session_open=session_open,
        vwap_monthly=monthly,
        vwap_weekly=weekly,
        vwap_intraday=intraday,
        cum_delta=cum_delta,
    )


def test_classify_position_above_below_and_at_with_tolerance():
    assert classify_position(105, 100) == Position.ABOVE
    assert classify_position(95, 100) == Position.BELOW
    assert classify_position(100.4, 100, tolerance=0.5) == Position.AT


def test_tier_report_bullish_when_price_above_all_tiers():
    state = _state(price=110, monthly=100, weekly=102, intraday=105)
    report = tier_report(state)
    assert report.monthly == Position.ABOVE
    assert report.weekly == Position.ABOVE
    assert report.intraday == Position.ABOVE
    assert report.structural_bias == StructuralBias.BULLISH


def test_tier_report_bearish_when_price_below_all_tiers():
    state = _state(price=90, monthly=100, weekly=102, intraday=105)
    assert tier_report(state).structural_bias == StructuralBias.BEARISH


def test_tier_report_neutral_when_tiers_disagree():
    # A genuine 3-way split (one ABOVE, one AT, one BELOW) -- no side
    # reaches the 2-of-3 majority structural_bias now needs, so this stays
    # NEUTRAL. Two tiers merely disagreeing while a third still sides with
    # one of them (e.g. ABOVE/BELOW/BELOW) is a majority read now, not a
    # neutral one -- see tiers.py's structural_bias docstring.
    state = _state(price=101, monthly=100, weekly=101, intraday=105)
    report = tier_report(state)
    assert report.monthly == Position.ABOVE
    assert report.weekly == Position.AT
    assert report.intraday == Position.BELOW
    assert report.structural_bias == StructuralBias.NEUTRAL


def test_classify_delta_insufficient_data_with_fewer_than_two_samples():
    assert classify_delta([], 1, 100) == DeltaSignal.INSUFFICIENT_DATA
    assert classify_delta([DeltaSample(100, 0)], 1, 100) == DeltaSignal.INSUFFICIENT_DATA


def test_classify_delta_absorption_when_delta_moves_but_price_does_not():
    samples = [DeltaSample(price=100.0, cum_delta=0), DeltaSample(price=100.1, cum_delta=500)]
    assert classify_delta(samples, price_move_threshold=1.0, delta_move_threshold=200) == DeltaSignal.ABSORPTION


def test_classify_delta_divergence_when_price_moves_but_delta_does_not():
    samples = [DeltaSample(price=100.0, cum_delta=0), DeltaSample(price=105.0, cum_delta=10)]
    assert classify_delta(samples, price_move_threshold=1.0, delta_move_threshold=200) == DeltaSignal.DIVERGENCE


def test_classify_delta_confirming_when_price_and_delta_agree():
    samples = [DeltaSample(price=100.0, cum_delta=0), DeltaSample(price=105.0, cum_delta=500)]
    assert classify_delta(samples, price_move_threshold=1.0, delta_move_threshold=200) == DeltaSignal.CONFIRMING


def test_classify_delta_divergence_when_price_and_delta_disagree():
    samples = [DeltaSample(price=100.0, cum_delta=0), DeltaSample(price=105.0, cum_delta=-500)]
    assert classify_delta(samples, price_move_threshold=1.0, delta_move_threshold=200) == DeltaSignal.DIVERGENCE


def test_classify_delta_neutral_when_neither_moves():
    samples = [DeltaSample(price=100.0, cum_delta=0), DeltaSample(price=100.1, cum_delta=10)]
    assert classify_delta(samples, price_move_threshold=1.0, delta_move_threshold=200) == DeltaSignal.NEUTRAL


def test_delta_history_tracks_oldest_and_newest_within_maxlen():
    history = DeltaHistory(maxlen=3)
    history.add(_state(price=100, monthly=1, weekly=1, intraday=1, cum_delta=0))
    history.add(_state(price=100.1, monthly=1, weekly=1, intraday=1, cum_delta=50))
    history.add(_state(price=100.2, monthly=1, weekly=1, intraday=1, cum_delta=100))
    history.add(_state(price=105, monthly=1, weekly=1, intraday=1, cum_delta=600))
    assert len(history) == 3  # oldest sample (cum_delta=0) evicted by maxlen

    signal = history.classify(price_move_threshold=1.0, delta_move_threshold=200)
    assert signal == DeltaSignal.CONFIRMING


_NEUTRAL_TIERS = TierReport(monthly=Position.ABOVE, weekly=Position.BELOW, intraday=Position.AT)
_BULLISH_TIERS = TierReport(monthly=Position.ABOVE, weekly=Position.ABOVE, intraday=Position.ABOVE)
_BEARISH_TIERS = TierReport(monthly=Position.BELOW, weekly=Position.BELOW, intraday=Position.BELOW)


def test_classify_regime_a_day_when_delta_balanced_and_bias_neutral():
    inputs = RegimeInputs(tier_report=_NEUTRAL_TIERS, cum_delta=200.0)
    assert classify_regime(inputs, delta_imbalance=1000.0) == Regime.A_DAY


def test_classify_regime_b_day_when_one_sided_delta_matches_bullish_bias():
    inputs = RegimeInputs(tier_report=_BULLISH_TIERS, cum_delta=2000.0)
    assert classify_regime(inputs, delta_imbalance=1000.0) == Regime.B_DAY


def test_classify_regime_b_day_when_one_sided_delta_matches_bearish_bias():
    inputs = RegimeInputs(tier_report=_BEARISH_TIERS, cum_delta=-2000.0)
    assert classify_regime(inputs, delta_imbalance=1000.0) == Regime.B_DAY


def test_classify_regime_unclear_when_signs_are_mixed():
    # Balanced delta (an A-day sign), but price accepted above all tiers (a
    # B-day sign) -- a genuinely mixed read.
    inputs = RegimeInputs(tier_report=_BULLISH_TIERS, cum_delta=200.0)
    assert classify_regime(inputs, delta_imbalance=1000.0) == Regime.UNCLEAR


def test_classify_regime_unclear_when_one_sided_delta_fights_the_bias():
    # Bullish structural bias but delta one-sided SELLING -- a divergence,
    # not a confirmed trend, so this must not be forced into B_DAY just
    # because both signs happen to be non-neutral.
    inputs = RegimeInputs(tier_report=_BULLISH_TIERS, cum_delta=-2000.0)
    assert classify_regime(inputs, delta_imbalance=1000.0) == Regime.UNCLEAR
