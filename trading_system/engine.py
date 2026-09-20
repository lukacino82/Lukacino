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
from .composite.models import Composite
from .hypothesis.delta import DeltaHistory, DeltaSignal, SessionDeltaTracker
from .hypothesis.formatter import format_hypothesis_text
from .hypothesis.generator import Hypothesis, generate_counter_intraday_hypothesis, generate_hypothesis
from .hypothesis.regime import Regime, RegimeInputs, classify_regime
from .hypothesis.synthesis import HTFBiasReport, SynthesisRegime, classify_counter_intraday, classify_htf_bias
from .hypothesis.tiers import TierReport, tier_report
from .risk.order import OrderProposal, build_order_proposal
from .risk.sizing import SizingConfig

NO_HYPOTHESIS_TEXT = "No hypothesis: regime unclear or price at the mean."


@dataclass(frozen=True)
class EngineResult:
    tier_report: TierReport
    delta_signal: DeltaSignal
    htf_bias: HTFBiasReport
    regime: Regime
    hypothesis: Optional[Hypothesis]
    proposal: Optional[OrderProposal]
    hypothesis_text: str


class LiveEngine:
    """One instance per instrument -- its DeltaHistory/SessionDeltaTracker
    need to persist across ticks within a session, not be rebuilt from a
    single snapshot.
    """

    def __init__(
        self,
        instrument: str,
        delta_window: int = 20,
        session_flush_threshold: float = 3000.0,
        session_reset_retracement_threshold: float = 1500.0,
        session_renewal_threshold: float = 1000.0,
    ) -> None:
        self.instrument = instrument
        self._delta_history = DeltaHistory(maxlen=delta_window)
        # Same "not calibrated" caveat as delta_imbalance elsewhere --
        # placeholders until checked against real per-instrument history.
        self._session_delta = SessionDeltaTracker(
            flush_threshold=session_flush_threshold,
            reset_retracement_threshold=session_reset_retracement_threshold,
            renewal_threshold=session_renewal_threshold,
        )
        self._last_session_open: Optional[float] = None

    def tick(
        self,
        state: LiveMarketState,
        composites: Sequence[Composite],
        sizing_config: SizingConfig,
        price_move_threshold: float,
        delta_move_threshold: float,
        delta_imbalance: float = 1000.0,
        rrr: Optional[float] = None,
        fixed_risk_distance: Optional[float] = None,
    ) -> EngineResult:
        self._delta_history.add(state)

        # session_open changes exactly once per trading day (ACSIL captures
        # it once at the session's first bar) -- the same per-session
        # marker used elsewhere as a day-boundary signal, here resetting
        # the session-long delta shape tracker so it doesn't blend
        # yesterday's flush/reset/renewed arc into today's.
        if self._last_session_open is not None and state.session_open != self._last_session_open:
            self._session_delta.reset()
        self._last_session_open = state.session_open
        self._session_delta.add(state)

        report = tier_report(state)
        delta_signal = self._delta_history.classify(price_move_threshold, delta_move_threshold)
        session_shape = self._session_delta.shape()

        # Multi-timeframe weighted synthesis (ARCHITECTURE.md item 8) is
        # checked FIRST: MM/HF bias opposed by the current intraday read,
        # confirmed by delta absorption/divergence or the session shape,
        # takes priority over the plain A/B-day read below. Falls through
        # unchanged to the existing regime.py/generate_hypothesis path
        # whenever the trigger doesn't fire (monthly AT, intraday agreeing
        # with the HTF bias, or no confirming delta signal) -- this is
        # additive, not a replacement, for every case the trigger doesn't
        # cover.
        htf_bias = classify_htf_bias(report, state)
        counter_signal = classify_counter_intraday(report, htf_bias, delta_signal, session_shape)

        if counter_signal.regime == SynthesisRegime.COUNTER_INTRADAY:
            regime = Regime.COUNTER_INTRADAY
            hypothesis = generate_counter_intraday_hypothesis(
                state, report, htf_bias, delta_signal, composites, rrr, fixed_risk_distance
            )
        else:
            # No closed-day profile is needed for this any more -- see
            # hypothesis/regime.py's module docstring -- so a hypothesis can
            # fire from the very first live tick of a fresh instrument.
            regime_inputs = RegimeInputs(tier_report=report, cum_delta=state.cum_delta)
            regime = classify_regime(regime_inputs, delta_imbalance)
            hypothesis = generate_hypothesis(state, regime, report, delta_signal, composites, rrr, fixed_risk_distance)

        proposal = build_order_proposal(self.instrument, hypothesis, sizing_config)
        text = format_hypothesis_text(hypothesis, proposal) if hypothesis is not None else NO_HYPOTHESIS_TEXT

        return EngineResult(
            tier_report=report,
            delta_signal=delta_signal,
            htf_bias=htf_bias,
            regime=regime,
            hypothesis=hypothesis,
            proposal=proposal,
            hypothesis_text=text,
        )
