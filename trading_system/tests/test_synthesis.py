"""Tests for hypothesis/synthesis.py -- the multi-timeframe weighted model.

test_counter_intraday_long_on_the_users_worked_scenario is the "first test
case" ARCHITECTURE.md item 8 asked for: MM bullish-cooling, HF in rotation,
intraday selloff with delta absorption -> a long.
"""

from datetime import datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.hypothesis.delta import (
    DeltaSample,
    DeltaSignal,
    SessionDeltaPhase,
    SessionDeltaSample,
    SessionDeltaShape,
    classify_delta,
)
from trading_system.hypothesis.generator import (
    Confluence,
    HypothesisType,
    generate_counter_intraday_hypothesis,
)
from trading_system.hypothesis.synthesis import (
    HTFConviction,
    SynthesisRegime,
    classify_counter_intraday,
    classify_htf_bias,
)
from trading_system.hypothesis.tiers import Position, StructuralBias, TierReport, tier_report

_NO_SHAPE = SessionDeltaShape(SessionDeltaPhase.INSUFFICIENT_DATA, None, None, None)


def _state(
    last_price: float,
    vwap_monthly: float,
    vwap_weekly: float,
    vwap_intraday: float,
    cum_delta: float,
    vwap_monthly_sd1: float = 0.0,
) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 20, 15, 0, 0),
        last_price=last_price,
        session_open=vwap_intraday,
        vwap_monthly=vwap_monthly,
        vwap_weekly=vwap_weekly,
        vwap_intraday=vwap_intraday,
        cum_delta=cum_delta,
        vwap_monthly_sd1=vwap_monthly_sd1,
    )


def test_classify_htf_bias_moderate_when_monthly_bullish_and_weekly_rotating():
    # MM above its VWAP (bullish), HF sitting AT its own VWAP (rotation --
    # no net weekly drift) -- the exact scenario's HTF read.
    report = TierReport(monthly=Position.ABOVE, weekly=Position.AT, intraday=Position.BELOW)
    state = _state(last_price=29500.0, vwap_monthly=29300.0, vwap_weekly=29500.0, vwap_intraday=29600.0, cum_delta=0.0)
    bias = classify_htf_bias(report, state)
    assert bias.direction == StructuralBias.BULLISH
    assert bias.conviction == HTFConviction.MODERATE


def test_classify_htf_bias_high_when_weekly_agrees_with_monthly():
    report = TierReport(monthly=Position.ABOVE, weekly=Position.ABOVE, intraday=Position.ABOVE)
    state = _state(last_price=110.0, vwap_monthly=100.0, vwap_weekly=105.0, vwap_intraday=100.0, cum_delta=0.0)
    assert classify_htf_bias(report, state).conviction == HTFConviction.HIGH


def test_classify_htf_bias_low_when_weekly_opposes_monthly():
    report = TierReport(monthly=Position.ABOVE, weekly=Position.BELOW, intraday=Position.ABOVE)
    state = _state(last_price=110.0, vwap_monthly=100.0, vwap_weekly=120.0, vwap_intraday=100.0, cum_delta=0.0)
    assert classify_htf_bias(report, state).conviction == HTFConviction.LOW


def test_classify_htf_bias_none_when_monthly_is_at():
    report = TierReport(monthly=Position.AT, weekly=Position.ABOVE, intraday=Position.ABOVE)
    state = _state(last_price=100.0, vwap_monthly=100.0, vwap_weekly=90.0, vwap_intraday=100.0, cum_delta=0.0)
    bias = classify_htf_bias(report, state)
    assert bias.direction == StructuralBias.NEUTRAL
    assert bias.conviction == HTFConviction.NONE


def test_moderate_conviction_upgraded_to_high_when_still_strongly_extended():
    # "Cooling" means retreated toward 1 SD; still outside ~2 SD-widths from
    # the monthly VWAP is the opposite -- a strong, still-live trend that
    # should outweigh a merely-rotating weekly tier.
    report = TierReport(monthly=Position.ABOVE, weekly=Position.AT, intraday=Position.ABOVE)
    state = _state(
        last_price=130.0, vwap_monthly=100.0, vwap_weekly=130.0, vwap_intraday=100.0,
        cum_delta=0.0, vwap_monthly_sd1=115.0,  # 1 SD width = 15; price is 30 away = 2.0x
    )
    bias = classify_htf_bias(report, state)
    assert bias.monthly_extension == 2.0
    assert bias.conviction == HTFConviction.HIGH


def test_classify_counter_intraday_none_when_htf_bias_is_none():
    report = TierReport(monthly=Position.AT, weekly=Position.ABOVE, intraday=Position.BELOW)
    state = _state(last_price=100.0, vwap_monthly=100.0, vwap_weekly=90.0, vwap_intraday=105.0, cum_delta=-5000.0)
    bias = classify_htf_bias(report, state)
    signal = classify_counter_intraday(report, bias, DeltaSignal.ABSORPTION, _NO_SHAPE)
    assert signal.regime == SynthesisRegime.NONE


def test_classify_counter_intraday_none_when_intraday_agrees_with_bias():
    # Bullish MM/HF and intraday ALSO above its own VWAP -- no conflict to
    # time an entry against, so this must not fire.
    report = TierReport(monthly=Position.ABOVE, weekly=Position.AT, intraday=Position.ABOVE)
    state = _state(last_price=110.0, vwap_monthly=100.0, vwap_weekly=110.0, vwap_intraday=105.0, cum_delta=0.0)
    bias = classify_htf_bias(report, state)
    signal = classify_counter_intraday(report, bias, DeltaSignal.ABSORPTION, _NO_SHAPE)
    assert signal.regime == SynthesisRegime.NONE


def test_classify_counter_intraday_none_when_delta_confirms_the_selloff():
    # Bullish HTF, intraday selloff, but delta CONFIRMS the selloff (real
    # conviction behind it, not absorption/divergence) -- no reversal signal.
    report = TierReport(monthly=Position.ABOVE, weekly=Position.AT, intraday=Position.BELOW)
    state = _state(last_price=29500.0, vwap_monthly=29300.0, vwap_weekly=29500.0, vwap_intraday=29600.0, cum_delta=-5000.0)
    bias = classify_htf_bias(report, state)
    signal = classify_counter_intraday(report, bias, DeltaSignal.CONFIRMING, _NO_SHAPE)
    assert signal.regime == SynthesisRegime.NONE


def test_counter_intraday_triggers_on_short_window_absorption():
    report = TierReport(monthly=Position.ABOVE, weekly=Position.AT, intraday=Position.BELOW)
    state = _state(last_price=29500.0, vwap_monthly=29300.0, vwap_weekly=29500.0, vwap_intraday=29600.0, cum_delta=-5000.0)
    bias = classify_htf_bias(report, state)
    signal = classify_counter_intraday(report, bias, DeltaSignal.ABSORPTION, _NO_SHAPE)
    assert signal.regime == SynthesisRegime.COUNTER_INTRADAY


def test_counter_intraday_triggers_on_session_shape_alone():
    # No short-window absorption/divergence read (NEUTRAL), but the whole
    # session shows a genuine renewed decline in cum_delta -- the second,
    # independent confirming path.
    report = TierReport(monthly=Position.ABOVE, weekly=Position.AT, intraday=Position.BELOW)
    state = _state(last_price=29500.0, vwap_monthly=29300.0, vwap_weekly=29500.0, vwap_intraday=29600.0, cum_delta=-5000.0)
    bias = classify_htf_bias(report, state)
    shape = SessionDeltaShape(SessionDeltaPhase.RENEWED_DOWN, -8000.0, -3000.0, -5000.0)
    signal = classify_counter_intraday(report, bias, DeltaSignal.NEUTRAL, shape)
    assert signal.regime == SynthesisRegime.COUNTER_INTRADAY


def test_counter_intraday_long_on_the_users_worked_scenario():
    """ARCHITECTURE.md item 8's worked scenario, end to end:

    MM (monthly) bullish but cooling: price sits above the monthly VWAP,
    well inside its own +1 SD band (not extended). HF (weekly) in rotation:
    price sits right AT the weekly VWAP, no net drift. Intraday shows a
    selloff: price below the intraday VWAP. Cumulative delta is negative
    (net aggressive selling) while price is nonetheless pushed *up* --
    classic absorption, read directly off the existing short-window
    classify_delta the same way the ARCHITECTURE.md doc describes it.

    Expected: a long, timed off the intraday extreme, in the direction of
    the higher-timeframe (monthly) bias.
    """
    vwap_monthly = 29300.0
    vwap_weekly = 29580.0  # == last_price -- HF sitting right at rotation
    vwap_intraday = 29650.0  # price below this -- the intraday "selloff" read
    last_price = 29580.0
    vwap_monthly_sd1 = 29550.0  # 1 SD width = 250; price is 280 away -- ~1.1x, i.e. "cooling" toward 1 SD

    state = _state(
        last_price=last_price,
        vwap_monthly=vwap_monthly,
        vwap_weekly=vwap_weekly,
        vwap_intraday=vwap_intraday,
        cum_delta=-4600.0,
        vwap_monthly_sd1=vwap_monthly_sd1,
    )
    report = tier_report(state)
    assert report.monthly == Position.ABOVE
    assert report.weekly == Position.AT
    assert report.intraday == Position.BELOW

    bias = classify_htf_bias(report, state)
    assert bias.direction == StructuralBias.BULLISH
    assert bias.conviction == HTFConviction.MODERATE
    assert bias.monthly_extension is not None and bias.monthly_extension < 2.0  # "cooling", not extended

    # Price pushed up (+5) while delta pushed down (-500 over the window) --
    # absorption/short-squeeze dynamics, exactly the DIVERGENCE the
    # ARCHITECTURE.md doc says this pattern already produces.
    delta_signal = classify_delta(
        [DeltaSample(price=last_price - 5.0, cum_delta=-4100.0), DeltaSample(price=last_price, cum_delta=-4600.0)],
        price_move_threshold=1.0,
        delta_move_threshold=200.0,
    )
    assert delta_signal == DeltaSignal.DIVERGENCE

    signal = classify_counter_intraday(report, bias, delta_signal, _NO_SHAPE)
    assert signal.regime == SynthesisRegime.COUNTER_INTRADAY

    hypothesis = generate_counter_intraday_hypothesis(
        state, report, bias, delta_signal, composites=(), fixed_risk_distance=50.0,
    )
    assert hypothesis is not None
    assert hypothesis.type == HypothesisType.COUNTER_LONG
    assert hypothesis.entry == last_price
    assert hypothesis.invalidation == last_price - 50.0
    assert hypothesis.confluence == Confluence.CLEAN  # MODERATE conviction -> CLEAN, not A_PLUS/WEAK
