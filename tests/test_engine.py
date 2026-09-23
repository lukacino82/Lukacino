import numpy as np
import pandas as pd
import pytest

from session_edge import BacktestConfig, RiskConfig, RangeBreakout, run_backtest, synthetic_intraday
from session_edge.data import load_csv
from session_edge.engine import daily_context
from session_edge.stats import breakeven_winrate, bootstrap_expectancy, deflated_sharpe, summary
from session_edge.validation import validate

TZ = "America/New_York"


def make_days(day2_bars):
    """Den 1 = rozcvička pro ATR (range 10 bodů), den 2 = testovací bary.
    Bary jsou 15min od 09:30; každá položka je (open, high, low, close)."""
    idx1 = pd.date_range("2024-01-02 09:30", periods=4, freq="15min", tz=TZ)
    d1 = pd.DataFrame([(100, 105, 95, 100)] * 4, index=idx1, columns=["open", "high", "low", "close"])
    idx2 = pd.date_range("2024-01-03 09:30", periods=len(day2_bars), freq="15min", tz=TZ)
    d2 = pd.DataFrame(day2_bars, index=idx2, columns=["open", "high", "low", "close"])
    return pd.concat([d1, d2]).astype(float)


def cfg(**kw):
    return BacktestConfig(risk=RiskConfig(**kw), atr_days=1)


STRAT = RangeBreakout(tz=TZ, range_start="09:30", range_end="10:00", entry_end="12:00")
# range 09:30–10:00: high 102, low 98 -> range 4
RANGE_BARS = [(100, 102, 99, 101), (101, 101.5, 98, 100)]


def test_long_breakout_hits_target():
    bars = RANGE_BARS + [(100, 102.5, 99.5, 102.2), (102.2, 111, 102, 110), (110, 111, 109, 110)]
    t = run_backtest(make_days(bars), STRAT, cfg(rrr=2.0))
    assert len(t) == 1
    row = t.iloc[0]
    assert row.direction == 1 and row.entry == 102 and row.stop == 98
    assert row.target == 110 and row.exit_reason == "target"
    assert row.r == pytest.approx(2.0)


def test_same_bar_stop_and_target_counts_as_stop():
    bars = RANGE_BARS + [(100, 102.5, 99.5, 102.2), (102.2, 111, 97, 100)]
    t = run_backtest(make_days(bars), STRAT, cfg(rrr=2.0))
    assert t.iloc[0].exit_reason == "stop"
    assert t.iloc[0].r == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open():
    bars = RANGE_BARS + [(100, 102.5, 99.5, 102.2), (96, 97, 95, 96)]
    t = run_backtest(make_days(bars), STRAT, cfg(rrr=2.0))
    assert t.iloc[0].exit == 96 and t.iloc[0].r == pytest.approx(-1.5)


def test_session_exit_time():
    bars = RANGE_BARS + [(100, 102.5, 99.5, 102.2), (102.2, 104, 101, 103), (103.5, 104, 103, 103.8)]
    # 5. bar začíná 10:30 -> nucené zavření na jeho open
    t = run_backtest(make_days(bars), STRAT, cfg(rrr=5.0, exit_time="10:30"))
    assert t.iloc[0].exit_reason == "time" and t.iloc[0].exit == 103.5


def test_costs_and_fixed_points_stop():
    bars = RANGE_BARS + [(100, 102.5, 100.5, 102.2), (102.2, 106.5, 102, 106)]
    t = run_backtest(make_days(bars), STRAT, cfg(stop_mode="points", stop_value=2, rrr=2, cost_per_trade=0.5))
    assert t.iloc[0].target == 106
    assert t.iloc[0].r == pytest.approx((4 - 0.5) / 2)


def test_max_trades_per_day():
    # long průraz -> stop (100.5), pak short průraz pod 98 -> target (95)
    bars = RANGE_BARS + [(100, 102.5, 101, 102.2), (102.2, 102.3, 99, 99.2),
                         (99.2, 99.3, 97.5, 97.8), (97.8, 98, 94, 94.5)]
    rc = dict(stop_mode="points", stop_value=1.5, rrr=2.0)
    one = run_backtest(make_days(bars), STRAT, cfg(max_trades_per_day=1, **rc))
    two = run_backtest(make_days(bars), STRAT, cfg(max_trades_per_day=2, **rc))
    assert len(one) == 1
    assert len(two) == 2 and list(two.direction) == [1, -1]
    assert list(two.exit_reason) == ["stop", "target"]


def test_breakeven_stop():
    bars = RANGE_BARS + [(100, 102.5, 99.5, 102.2), (102.2, 106.5, 102, 106), (106, 106, 101, 101)]
    t = run_backtest(make_days(bars), STRAT, cfg(rrr=3.0, breakeven_at_r=1.0))
    assert t.iloc[0].exit_reason == "breakeven" and t.iloc[0].r == pytest.approx(0.0)


def test_atr_has_no_lookahead():
    df = synthetic_intraday(days=30, seed=1)
    d = daily_context(df.tz_convert(TZ), atr_days=5)
    changed = df.copy()
    last = changed.index.date == changed.index.date[-1]
    changed.loc[last, "high"] *= 2  # změna posledního dne nesmí ovlivnit jeho ATR
    d2 = daily_context(changed.tz_convert(TZ), atr_days=5)
    assert d["atr"].iloc[-1] == pytest.approx(d2["atr"].iloc[-1])


def test_stats_basics():
    assert breakeven_winrate(2.0) == pytest.approx(1 / 3)
    b = bootstrap_expectancy(np.array([1.0, 1.2, 0.8, 1.1] * 10))
    assert b["ci_low"] > 0 and b["prob_le_zero"] == 0
    r = np.random.default_rng(0).normal(0.3, 1, 400)
    assert deflated_sharpe(r, n_trials=1)["dsr"] > deflated_sharpe(r, n_trials=1000)["dsr"]


def test_random_walk_has_no_edge_and_injected_edge_is_found():
    rc = RiskConfig(rrr=2.0, exit_time="15:55")
    noise = validate(synthetic_intraday(days=400, seed=3), STRAT, BacktestConfig(risk=rc), n_random=30)
    assert not noise["checks"]["lepší než náhodný směr (p < 0.05)"] or noise["summary"]["t_stat"] < 2
    edge = validate(synthetic_intraday(days=400, seed=3, orb_drift=0.2), STRAT,
                    BacktestConfig(risk=rc), n_random=30)
    assert edge["random_direction"]["p_value"] < 0.05 and edge["bootstrap"]["ci_low"] > 0


def test_load_mt5_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\n"
                 "2024.01.02\t14:30:00\t1\t2\t0.5\t1.5\t10\n"
                 "2024.01.02\t14:35:00\t1.5\t2\t1\t1.2\t12\n")
    df = load_csv(str(p), tz="UTC", sep="\t")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is not None and len(df) == 2
    assert summary(pd.DataFrame(columns=["r", "date", "exit_reason"]))["trades"] == 0


def test_load_ninjatrader_txt(tmp_path):
    p = tmp_path / "es.txt"
    p.write_text("20240102 093100;4700.25;4701.5;4699.75;4701;1200\n"
                 "20240102 093200;4701;4702;4700.5;4701.75;900\n"
                 "20240102 093300;4701.75;4703;4701.5;4702.5;800\n")
    df = load_csv(str(p), tz="America/New_York", bar_time="close")
    assert df.index[0] == pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    assert df["close"].iloc[-1] == 4702.5 and df["volume"].iloc[0] == 1200
