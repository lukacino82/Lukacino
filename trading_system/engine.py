"""Per-tick orchestration: live_state.csv snapshot -> Hypothesis -> text.

This is pure logic -- everything is fed in and returned, no file I/O -- so
it's unit-testable without a real bridge directory. A thin runner script
that actually polls real bridge files (live_state.csv, daily_profile_export
.csv, composites.csv) and writes hypothesis.txt still needs to be built,
and needs a decision on where it runs continuously (same Windows machine as
Sierra Chart, most likely) before it's wired up for real -- see
ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .bridge.csv_bridge import LiveMarketState
from .composite.models import Composite, DailyProfile
from .hypothesis.delta import DeltaHistory, DeltaSignal
from .hypothesis.formatter import format_hypothesis_text
from .hypothesis.generator import Hypothesis, generate_hypothesis
from .hypothesis.regime import Regime, RegimeInputs, classify_regime
from .hypothesis.tiers import TierReport, tier_report
from .risk.order import OrderProposal, build_order_proposal
from .risk.sizing import SizingConfig

NO_HYPOTHESIS_TEXT = "No hypothesis: regime unclear or price at the mean."


@dataclass(frozen=True)
class EngineResult:
    tier_report: TierReport
    delta_signal: DeltaSignal
    regime: Regime
    hypothesis: Optional[Hypothesis]
    proposal: Optional[OrderProposal]
    hypothesis_text: str


class LiveEngine:
    """One instance per instrument -- its DeltaHistory needs to persist
    across ticks within a session, not be rebuilt from a single snapshot.
    """

    def __init__(self, instrument: str, delta_window: int = 20) -> None:
        self.instrument = instrument
        self._delta_history = DeltaHistory(maxlen=delta_window)

    def tick(
        self,
        state: LiveMarketState,
        yesterday: Optional[DailyProfile],
        composites: Sequence[Composite],
        sizing_config: SizingConfig,
        price_move_threshold: float,
        delta_move_threshold: float,
        gap_threshold_fraction: float = 0.25,
        delta_imbalance: float = 1000.0,
    ) -> EngineResult:
        self._delta_history.add(state)
        report = tier_report(state)
        delta_signal = self._delta_history.classify(price_move_threshold, delta_move_threshold)

        if yesterday is not None:
            regime_inputs = RegimeInputs(
                session_open=state.session_open,
                yesterday=yesterday,
                tier_report=report,
                cum_delta=state.cum_delta,
            )
            regime = classify_regime(regime_inputs, gap_threshold_fraction, delta_imbalance)
        else:
            # No closed-day profile yet (e.g. very first session) -- the
            # gap-vs-value-area test has nothing to compare against.
            regime = Regime.UNCLEAR

        hypothesis = generate_hypothesis(state, regime, report, delta_signal, composites)
        proposal = build_order_proposal(self.instrument, hypothesis, sizing_config)
        text = format_hypothesis_text(hypothesis, proposal) if hypothesis is not None else NO_HYPOTHESIS_TEXT

        return EngineResult(
            tier_report=report,
            delta_signal=delta_signal,
            regime=regime,
            hypothesis=hypothesis,
            proposal=proposal,
            hypothesis_text=text,
        )
