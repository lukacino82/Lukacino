"""Hierarchical, weighted multi-timeframe synthesis model.

See ARCHITECTURE.md item 8 ("Multi-timeframe weighted synthesis model") for
the full worked scenario this implements: monthly VWAP (MM) bullish but
cooling (price retreated from outside 2SD to inside 1SD, still above the
monthly VWAP line); weekly VWAP (HF) in rotation (no net weekly drift);
intraday shows a selloff (price below intraday VWAP); cumulative delta
negative (net aggressive selling) while price is nonetheless pushed *up*
into stops -- absorption/short-squeeze dynamics, not confirmed selling.
Correct read: a long, timed off the intraday extreme, in the direction of
the higher-timeframe (MM) bias.

This is a hierarchical model, not a bigger flat AND/OR gate (the existing
2-of-3 `TierReport.structural_bias` in tiers.py, which this does NOT
replace -- `hypothesis/regime.py`'s existing A_DAY/B_DAY path still uses
it unchanged):
- MM (monthly) alone sets the *strategic* long/short direction -- it's the
  slowest-moving and least prone to whipsaw of the three tiers.
- HF (weekly) modulates *confidence* in that bias rather than voting
  equally against it: agreeing raises conviction, rotating (AT) lowers it
  without vetoing it, opposing lowers it further -- still never flips the
  direction, which MM alone owns.
- Intraday sets *entry timing*, not direction. An intraday read that
  opposes the MM/HF bias, confirmed by a delta absorption/divergence
  signal at that extreme (the existing short-window `DeltaSignal`, or the
  session-long flush/reset/renewed shape from `delta.py` agreeing), is the
  specific trigger for a counter-intraday, pro-higher-timeframe entry.

Deliberately still returns "no trigger" (`SynthesisRegime.NONE`) often --
the goal is narrowing which cases are genuinely ambiguous, not eliminating
UNCLEAR altogether. Every threshold here (the extension ratio needed to
upgrade MODERATE to HIGH conviction) is a placeholder needing the same
real-data calibration flagged everywhere else in this file/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..bridge.csv_bridge import LiveMarketState
from .delta import DeltaSignal, SessionDeltaPhase, SessionDeltaShape
from .tiers import Position, StructuralBias, TierReport


class HTFConviction(Enum):
    NONE = "none"  # MM itself is AT its VWAP -- no strategic bias to have conviction in
    LOW = "low"  # HF actively opposes MM
    MODERATE = "moderate"  # HF is rotating (no net drift) -- a real bias, just not confirmed
    HIGH = "high"  # HF agrees with MM, or MM is strongly extended despite a rotating HF


@dataclass(frozen=True)
class HTFBiasReport:
    direction: StructuralBias  # BULLISH/BEARISH from MM alone; NEUTRAL only when MM is AT
    conviction: HTFConviction
    # How many "SD1-widths" price sits from the monthly VWAP (i.e. price's
    # distance from vwap_monthly divided by the monthly study's own +-1SD
    # band width) -- None when ACSIL hasn't supplied vwap_monthly_sd1 yet.
    # Purely informational except for the HIGH-conviction upgrade below;
    # this is how "bullish but cooling" (retreated from ~2 toward ~1) gets
    # represented as a number instead of a bare above/below read.
    monthly_extension: Optional[float]


def classify_htf_bias(
    tier_report: TierReport,
    state: LiveMarketState,
    strong_extension_ratio: float = 2.0,
) -> HTFBiasReport:
    if tier_report.monthly == Position.AT:
        return HTFBiasReport(StructuralBias.NEUTRAL, HTFConviction.NONE, None)

    direction = StructuralBias.BULLISH if tier_report.monthly == Position.ABOVE else StructuralBias.BEARISH

    if tier_report.weekly == tier_report.monthly:
        conviction = HTFConviction.HIGH
    elif tier_report.weekly == Position.AT:
        conviction = HTFConviction.MODERATE
    else:
        conviction = HTFConviction.LOW

    monthly_extension: Optional[float] = None
    if state.vwap_monthly_sd1 > 0:
        sd1_distance = abs(state.vwap_monthly_sd1 - state.vwap_monthly)
        if sd1_distance > 0:
            monthly_extension = abs(state.last_price - state.vwap_monthly) / sd1_distance

    # A monthly trend still strongly extended (not actually "cooling")
    # can outweigh a merely-rotating weekly tier -- HF's own read is what
    # sets the conviction *tier* otherwise, per the agreed design.
    if conviction == HTFConviction.MODERATE and monthly_extension is not None and monthly_extension >= strong_extension_ratio:
        conviction = HTFConviction.HIGH

    return HTFBiasReport(direction=direction, conviction=conviction, monthly_extension=monthly_extension)


class SynthesisRegime(Enum):
    COUNTER_INTRADAY = "counter_intraday"
    NONE = "none"  # no trigger this tick -- caller falls back to the existing A/B-day model


@dataclass(frozen=True)
class CounterIntradaySignal:
    regime: SynthesisRegime
    htf_bias: HTFBiasReport


def classify_counter_intraday(
    tier_report: TierReport,
    htf_bias: HTFBiasReport,
    delta_signal: DeltaSignal,
    session_shape: SessionDeltaShape,
) -> CounterIntradaySignal:
    """The one new trigger this model adds -- see module docstring for the
    full worked scenario.

    No conviction floor beyond HTFConviction.NONE (MM itself flat) is
    enforced here -- LOW-conviction cases still produce a signal; sizing
    that down is `generate_counter_intraday_hypothesis`'s confluence
    scoring's job, the same way CLEAN/WEAK already size down the existing
    A/B-day hypotheses.
    """
    if htf_bias.conviction == HTFConviction.NONE:
        return CounterIntradaySignal(SynthesisRegime.NONE, htf_bias)

    bullish = htf_bias.direction == StructuralBias.BULLISH
    intraday_opposes = (
        (bullish and tier_report.intraday == Position.BELOW)
        or (not bullish and tier_report.intraday == Position.ABOVE)
    )
    if not intraday_opposes:
        return CounterIntradaySignal(SynthesisRegime.NONE, htf_bias)

    # The short-window absorption/divergence read at the intraday extreme --
    # exactly the user's "price up / delta down" pattern, already produced
    # by delta.py's existing classify_delta.
    delta_confirms_extreme = delta_signal in (DeltaSignal.ABSORPTION, DeltaSignal.DIVERGENCE)

    # OR the whole-session flush/reset/renewed shape showing a genuine
    # renewed leg in the direction opposing the HTF bias -- a second,
    # independent way of recognizing the same underlying phenomenon (the
    # current price extreme is backed by a real, validated delta leg, not
    # just tick noise) over a longer window.
    opposing_phase = SessionDeltaPhase.RENEWED_DOWN if bullish else SessionDeltaPhase.RENEWED_UP
    session_confirms = session_shape.phase == opposing_phase

    if not (delta_confirms_extreme or session_confirms):
        return CounterIntradaySignal(SynthesisRegime.NONE, htf_bias)

    return CounterIntradaySignal(SynthesisRegime.COUNTER_INTRADAY, htf_bias)
