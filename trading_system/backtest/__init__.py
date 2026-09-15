"""Historical replay of LiveEngine against past daily profiles + intraday snapshots.

See ``replay.py`` for the entry point (``run_backtest``) and the module
docstring there for the design (lookahead avoidance, trade lifecycle, R-multiple).
"""

from __future__ import annotations

from .replay import BacktestConfig, BacktestReport, TradeResult, TradeStatus, run_backtest

__all__ = [
    "BacktestConfig",
    "BacktestReport",
    "TradeResult",
    "TradeStatus",
    "run_backtest",
]
