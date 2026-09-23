"""session_edge – jednoduché intradenní systémy nad nejvolatilnějšími okny seance
a statistický aparát, který rozhodne, zda mají skutečnou hranu."""
from .config import BacktestConfig, RiskConfig
from .data import load_csv, synthetic_intraday
from .engine import run_backtest
from .strategies import (FailedBreakoutFade, GapFade, IntradayMomentum, PRESETS,
                         RangeBreakout, make_strategy)
from .validation import param_grid, validate, walk_forward

__all__ = [
    "BacktestConfig", "RiskConfig", "load_csv", "synthetic_intraday", "run_backtest",
    "RangeBreakout", "FailedBreakoutFade", "IntradayMomentum", "GapFade", "PRESETS",
    "make_strategy", "validate", "walk_forward", "param_grid",
]
