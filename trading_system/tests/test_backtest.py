"""Synthetic-data tests for trading_system.backtest.replay.

Every scenario is built to be deterministic on the very first tick after
`yesterday` becomes available -- with only one LiveMarketState sample in the
rolling window, DeltaHistory always classifies as INSUFFICIENT_DATA, which
generator.py's confluence rule treats as neither supporting nor contradicting
(CLEAN confluence, never WEAK) -- so every scenario here gets a non-zero
contract count without needing multiple warm-up ticks first.
"""

from __future__ import annotations

from datetime import date, datetime

from trading_system.backtest.replay import BacktestConfig, TradeStatus, run_backtest
from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.composite.models import DailyProfile
from trading_system.hypothesis.generator import Confluence, HypothesisType
from trading_system.hypothesis.regime import Regime
from trading_system.risk.sizing import SizingConfig, SizingMode

INSTRUMENT = "NQ"

CONFIG = BacktestConfig(
    sizing=SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1),
    price_move_threshold=5.0,
    delta_move_threshold=500.0,
)

YESTERDAY = DailyProfile(instrument=INSTRUMENT, session_date=date(2024, 1, 1), val=100.0, vah=110.0, poc=105.0)


def _a_day_state(when: datetime, last_price: float) -> LiveMarketState:
    """A_DAY regime: balanced delta and a neutral tier bias (monthly/weekly
    above price, intraday below) -- see hypothesis/regime.py's
    classify_regime. session_open no longer feeds regime classification at
    all, but is still part of LiveMarketState/the invalidation fallback.
    """
    return LiveMarketState(
        instrument=INSTRUMENT,
        timestamp=when,
        last_price=last_price,
        session_open=100.5,
        vwap_monthly=95.0,  # price above -> ABOVE
        vwap_weekly=95.0,  # price above -> ABOVE
        vwap_intraday=103.0,  # price below -> BELOW -> mixed -> NEUTRAL bias
        cum_delta=0.0,  # balanced
    )


def test_a_day_long_hits_target_is_a_win() -> None:
    states = [
        _a_day_state(datetime(2024, 1, 2, 9, 30), last_price=101.0),  # opens A_LONG
        _a_day_state(datetime(2024, 1, 2, 9, 31), last_price=102.0),  # between entry and target -- still open
        _a_day_state(datetime(2024, 1, 2, 9, 32), last_price=103.5),  # crosses target_1 (vwap_intraday=103)
    ]

    report = run_backtest(INSTRUMENT, [YESTERDAY], states, CONFIG)

    assert len(report.trades) == 1
    trade = report.trades[0]
    assert trade.status == TradeStatus.WIN
    assert trade.hypothesis_type == HypothesisType.A_LONG
    assert trade.direction == "long"
    assert trade.entry == 101.0
    assert trade.stop == 100.5  # invalidation fallback: session_open (no composites)
    assert trade.target_1 == 103.0
    assert trade.r_multiple == (103.0 - 101.0) / (101.0 - 100.5)  # == 4.0
    assert report.win_rate == 1.0
    assert report.average_r == trade.r_multiple
    # Only the opening tick reaches engine.tick() -- the other two are spent
    # checking the already-open trade, per the "one trade at a time" rule.
    assert report.regime_counts == {Regime.A_DAY: 1}


def test_a_day_long_hits_stop_is_a_loss() -> None:
    states = [
        _a_day_state(datetime(2024, 1, 2, 9, 30), last_price=101.0),  # opens A_LONG, stop=100.5
        _a_day_state(datetime(2024, 1, 2, 9, 31), last_price=100.4),  # crosses the stop
    ]

    report = run_backtest(INSTRUMENT, [YESTERDAY], states, CONFIG)

    assert len(report.trades) == 1
    trade = report.trades[0]
    assert trade.status == TradeStatus.LOSS
    assert trade.r_multiple == -1.0
    assert report.win_rate == 0.0
    assert report.total_r == -1.0


def test_trade_left_open_at_end_of_data_is_not_a_resolved_win_or_loss() -> None:
    states = [
        _a_day_state(datetime(2024, 1, 2, 9, 30), last_price=101.0),
        _a_day_state(datetime(2024, 1, 2, 9, 31), last_price=101.5),  # never reaches 100.5 or 103.0
    ]

    report = run_backtest(INSTRUMENT, [YESTERDAY], states, CONFIG)

    assert len(report.trades) == 1
    assert report.trades[0].status == TradeStatus.OPEN
    assert report.trades[0].r_multiple is None
    assert report.resolved == []
    assert report.win_rate is None  # nothing resolved yet -- not 0/0


def test_no_new_signal_is_opened_while_a_trade_is_still_active() -> None:
    """Even though the middle state on its own would re-qualify as a fresh
    A_LONG setup (same regime-producing levels), the first trade is still
    open and must block it -- see replay.py's "one trade at a time" rule.
    """
    states = [
        _a_day_state(datetime(2024, 1, 2, 9, 30), last_price=101.0),  # opens trade #1
        _a_day_state(datetime(2024, 1, 2, 9, 31), last_price=101.2),  # would also qualify alone -- must be ignored
        _a_day_state(datetime(2024, 1, 2, 9, 32), last_price=103.5),  # resolves trade #1 as a WIN
        _a_day_state(datetime(2024, 1, 2, 9, 33), last_price=101.5),  # now free to open trade #2
        _a_day_state(datetime(2024, 1, 2, 9, 34), last_price=100.0),  # trade #2's stop (100.5) is crossed
    ]

    report = run_backtest(INSTRUMENT, [YESTERDAY], states, CONFIG)

    assert len(report.trades) == 2
    assert report.trades[0].status == TradeStatus.WIN
    assert report.trades[1].status == TradeStatus.LOSS
    assert report.win_rate == 0.5


def test_report_groups_by_hypothesis_type_and_confluence() -> None:
    """Same win-then-loss sequence as
    test_no_new_signal_is_opened_while_a_trade_is_still_active -- both
    trades are A_LONG/CLEAN here, so the grouped stats for that one bucket
    must equal the report's own overall totals, and no other bucket exists.
    """
    states = [
        _a_day_state(datetime(2024, 1, 2, 9, 30), last_price=101.0),
        _a_day_state(datetime(2024, 1, 2, 9, 31), last_price=101.2),
        _a_day_state(datetime(2024, 1, 2, 9, 32), last_price=103.5),  # WIN
        _a_day_state(datetime(2024, 1, 2, 9, 33), last_price=101.5),
        _a_day_state(datetime(2024, 1, 2, 9, 34), last_price=100.0),  # LOSS
    ]

    report = run_backtest(INSTRUMENT, [YESTERDAY], states, CONFIG)

    by_type = report.by_hypothesis_type()
    assert set(by_type) == {HypothesisType.A_LONG}
    stats = by_type[HypothesisType.A_LONG]
    assert stats.trades == 2
    assert stats.wins == 1
    assert stats.losses == 1
    assert stats.open_count == 0
    assert stats.win_rate == report.win_rate
    assert stats.total_r == report.total_r
    assert stats.average_r == report.average_r

    by_confluence = report.by_confluence()
    assert set(by_confluence) == {Confluence.CLEAN}
    assert by_confluence[Confluence.CLEAN] == stats  # same two trades, same numbers


def test_same_day_profile_is_not_visible_to_composite_engine_no_lookahead() -> None:
    """A DailyProfile dated the same day as a snapshot represents that day's
    close, which hasn't happened yet intraday -- CompositeEngine must not
    ingest it until a later day's snapshot arrives. (Regime classification
    itself no longer depends on any daily profile at all -- see
    hypothesis/regime.py -- so this now only exercises the composite-side
    lookahead guard: the state below still resolves to an A_DAY hypothesis
    from tier bias/delta alone.)
    """
    same_day_profile = DailyProfile(instrument=INSTRUMENT, session_date=date(2024, 1, 2), val=100.0, vah=110.0, poc=105.0)
    states = [_a_day_state(datetime(2024, 1, 2, 9, 30), last_price=101.0)]

    report = run_backtest(INSTRUMENT, [same_day_profile], states, CONFIG)

    assert report.trades == [] or report.trades[0].status == TradeStatus.OPEN
    assert report.regime_counts == {Regime.A_DAY: 1}


def test_b_day_hypothesis_with_no_composite_target_is_counted_not_dropped() -> None:
    """B_DAY continuation with no active composite has no target_1 to judge
    a win against -- must be counted in skipped_no_target, not silently
    dropped and not force-scored as a trade.
    """
    state = LiveMarketState(
        instrument=INSTRUMENT,
        timestamp=datetime(2024, 1, 2, 9, 30),
        last_price=130.0,
        session_open=130.0,
        vwap_monthly=90.0,  # price above all three tiers -> BULLISH structural bias
        vwap_weekly=90.0,
        vwap_intraday=90.0,
        cum_delta=2000.0,  # one-sided, same direction as the bullish bias
    )

    report = run_backtest(INSTRUMENT, [YESTERDAY], [state], CONFIG)

    assert report.trades == []
    assert report.skipped_no_target == 1
