from datetime import datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.hypothesis.delta import (
    DeltaHistory,
    DeltaSample,
    DeltaSignal,
    classify_delta,
)
from trading_system.hypothesis.tiers import (
    Position,
    StructuralBias,
    classify_position,
    tier_report,
)


def _state(price: float, monthly: float, weekly: float, intraday: float, cum_delta: float = 0) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 9, 0, 0),
        last_price=price,
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
    state = _state(price=101, monthly=100, weekly=102, intraday=105)
    report = tier_report(state)
    assert report.monthly == Position.ABOVE
    assert report.weekly == Position.BELOW
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
