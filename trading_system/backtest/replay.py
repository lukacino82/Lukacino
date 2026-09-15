"""Historical replay of LiveEngine over past daily profiles + intraday snapshots.

Turns a chronological history of DailyProfile rows (the same shape as a real,
accumulated daily_profile_export.csv) and LiveMarketState snapshots (the same
shape as live_state.csv, but many rows instead of one) into a report of what
LiveEngine would have signalled and how those signals would have played out --
before anything trades on a real account, per ARCHITECTURE.md's backtest step.

Lookahead avoidance is the whole point of doing this as a replay rather than
just calling generate_hypothesis() against the full history at once:
- A day's DailyProfile only becomes visible to CompositeEngine, and only
  becomes "yesterday" for regime classification, once the intraday clock has
  actually passed that day -- exactly the constraint production's
  run_live.py gets for free (ACSIL never writes a day's row until that day
  has actually closed), which a replay fed the whole history upfront has to
  enforce explicitly instead.
- Only one trade is tracked open at a time, matching the SEMI_AUTO mental
  model of one trader watching one instrument, not a portfolio backtester
  running independent parallel positions. A new signal while one is already
  open is simply not evaluated -- it isn't queued or merged.

Trade outcome (win/loss/open) is judged only against target_1 vs. the
invalidation (stop) -- target_2/runner are recorded as "also reached" flags
for extra context, but don't change the primary win/loss call. A hypothesis
with no target_1 (an unopposed B-day continuation with no composite target)
has nothing to call a win against, so it's counted separately rather than
silently skipped or forced into a made-up outcome. Every check works off
LiveMarketState.last_price snapshots, not real OHLC bars, so there's no true
intrabar high/low -- if a single step between two snapshots would cross both
the stop and the target, the stop wins (the conservative assumption, since
the real order can't be known from a single point sample).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence

from ..bridge.csv_bridge import LiveMarketState
from ..composite.engine import CompositeEngine
from ..composite.models import DailyProfile
from ..engine import LiveEngine
from ..hypothesis.generator import Confluence, HypothesisType
from ..risk.sizing import SizingConfig


class TradeStatus(Enum):
    WIN = "win"
    LOSS = "loss"
    OPEN = "open"  # never hit target_1 or stop before the data ran out


@dataclass(frozen=True)
class TradeResult:
    instrument: str
    hypothesis_type: HypothesisType
    confluence: Confluence
    direction: str  # "long" or "short"
    entry: float
    stop: float
    target_1: float
    opened_at: datetime
    status: TradeStatus
    closed_at: Optional[datetime]
    r_multiple: Optional[float]  # None while status is OPEN
    target_2_reached: bool = False
    runner_reached: bool = False


@dataclass
class BacktestReport:
    trades: List[TradeResult] = field(default_factory=list)
    skipped_no_target: int = 0  # actionable hypotheses with no target_1 to judge a win against

    @property
    def resolved(self) -> List[TradeResult]:
        return [t for t in self.trades if t.status != TradeStatus.OPEN]

    @property
    def wins(self) -> List[TradeResult]:
        return [t for t in self.trades if t.status == TradeStatus.WIN]

    @property
    def losses(self) -> List[TradeResult]:
        return [t for t in self.trades if t.status == TradeStatus.LOSS]

    @property
    def win_rate(self) -> Optional[float]:
        resolved = self.resolved
        if not resolved:
            return None
        return len(self.wins) / len(resolved)

    @property
    def total_r(self) -> float:
        return sum(t.r_multiple for t in self.resolved if t.r_multiple is not None)

    @property
    def average_r(self) -> Optional[float]:
        resolved = self.resolved
        if not resolved:
            return None
        return self.total_r / len(resolved)


@dataclass(frozen=True)
class BacktestConfig:
    """The same per-instrument thresholds run_live.py's InstrumentConfig
    carries -- kept as a separate type here rather than importing run_live's
    (a runner script, not a library module other code should depend on).
    """

    sizing: SizingConfig
    price_move_threshold: float
    delta_move_threshold: float
    gap_threshold_fraction: float = 0.25
    delta_imbalance: float = 1000.0
    delta_window: int = 20


@dataclass
class _OpenTrade:
    instrument: str
    hypothesis_type: HypothesisType
    confluence: Confluence
    direction: str
    entry: float
    stop: float
    target_1: float
    target_2: Optional[float]
    runner: Optional[float]
    opened_at: datetime
    target_2_reached: bool = False
    runner_reached: bool = False

    def _favorable_level_hit(self, level: float, price: float) -> bool:
        """True once price has moved to ``level`` in this trade's favor
        (used for target_1/target_2/runner, which all sit on the same side).
        """
        return price >= level if self.direction == "long" else price <= level

    def check(self, price: float, at: datetime) -> Optional[TradeResult]:
        """Returns a resolved TradeResult once the stop or target_1 is
        crossed, else None (still open) after updating the target_2/runner
        "also reached" flags in place.
        """
        # The stop sits on the *opposite* side from targets, so it's the
        # mirror image of _favorable_level_hit rather than a call to it.
        stop_hit = price <= self.stop if self.direction == "long" else price >= self.stop
        target_hit = self._favorable_level_hit(self.target_1, price)

        if self.target_2 is not None and self._favorable_level_hit(self.target_2, price):
            self.target_2_reached = True
        if self.runner is not None and self._favorable_level_hit(self.runner, price):
            self.runner_reached = True

        if not stop_hit and not target_hit:
            return None

        risk = abs(self.entry - self.stop)
        if stop_hit:
            # Conservative: an ambiguous single-step move that could have
            # crossed both counts as the stop, per the module docstring.
            status = TradeStatus.LOSS
            r_multiple = -1.0
        else:
            status = TradeStatus.WIN
            r_multiple = abs(self.target_1 - self.entry) / risk if risk > 0 else None

        return TradeResult(
            instrument=self.instrument,
            hypothesis_type=self.hypothesis_type,
            confluence=self.confluence,
            direction=self.direction,
            entry=self.entry,
            stop=self.stop,
            target_1=self.target_1,
            opened_at=self.opened_at,
            status=status,
            closed_at=at,
            r_multiple=r_multiple,
            target_2_reached=self.target_2_reached,
            runner_reached=self.runner_reached,
        )


def run_backtest(
    instrument: str,
    daily_profiles: Sequence[DailyProfile],
    intraday_states: Sequence[LiveMarketState],
    config: BacktestConfig,
) -> BacktestReport:
    """Replays ``intraday_states`` through LiveEngine in chronological order,
    using ``daily_profiles`` (any order -- sorted here) as the closed-day
    history CompositeEngine/regime classification would have actually seen
    at each point in time, and tracks every actionable hypothesis's outcome.
    """
    profiles = sorted(
        (p for p in daily_profiles if p.instrument == instrument),
        key=lambda p: p.session_date,
    )
    states = sorted(
        (s for s in intraday_states if s.instrument == instrument),
        key=lambda s: s.timestamp,
    )

    composite_engine = CompositeEngine()
    engine = LiveEngine(instrument, delta_window=config.delta_window)
    report = BacktestReport()

    profile_idx = 0
    yesterday: Optional[DailyProfile] = None
    open_trade: Optional[_OpenTrade] = None

    for state in states:
        # Ingest every profile that closed strictly before this snapshot's
        # date -- see the module docstring on why this can't just ingest
        # everything in `profiles` up front.
        while profile_idx < len(profiles) and profiles[profile_idx].session_date < state.timestamp.date():
            composite_engine.ingest_day(profiles[profile_idx])
            yesterday = profiles[profile_idx]
            profile_idx += 1

        if open_trade is not None:
            result = open_trade.check(state.last_price, state.timestamp)
            if result is not None:
                report.trades.append(result)
                open_trade = None
            # An open trade blocks new signals until it resolves -- see the
            # module docstring's "one trade at a time" rule -- so this
            # snapshot is spent either updating or closing it, never both
            # closing it and opening a fresh one in the same tick.
            continue

        result = engine.tick(
            state,
            yesterday,
            composite_engine.composites,
            config.sizing,
            config.price_move_threshold,
            config.delta_move_threshold,
            config.gap_threshold_fraction,
            config.delta_imbalance,
        )
        if result.proposal is None:
            continue
        if result.hypothesis is None or result.hypothesis.target_1 is None:
            # build_order_proposal already screens out WEAK confluence / 0
            # contracts; a live proposal with no target_1 at all still can't
            # be judged a win/loss against anything, so it's counted
            # separately rather than silently dropped or force-scored.
            report.skipped_no_target += 1
            continue

        open_trade = _OpenTrade(
            instrument=instrument,
            hypothesis_type=result.hypothesis.type,
            confluence=result.hypothesis.confluence,
            direction=result.proposal.direction,
            entry=result.hypothesis.entry,
            stop=result.hypothesis.invalidation,
            target_1=result.hypothesis.target_1,
            target_2=result.hypothesis.target_2,
            runner=result.hypothesis.runner,
            opened_at=state.timestamp,
        )

    if open_trade is not None:
        report.trades.append(
            TradeResult(
                instrument=open_trade.instrument,
                hypothesis_type=open_trade.hypothesis_type,
                confluence=open_trade.confluence,
                direction=open_trade.direction,
                entry=open_trade.entry,
                stop=open_trade.stop,
                target_1=open_trade.target_1,
                opened_at=open_trade.opened_at,
                status=TradeStatus.OPEN,
                closed_at=None,
                r_multiple=None,
                target_2_reached=open_trade.target_2_reached,
                runner_reached=open_trade.runner_reached,
            )
        )

    return report
