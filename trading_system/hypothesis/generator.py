"""Turns a regime + tier + delta read into one concrete hypothesis.

Mirrors the `trading-vwap-hypotezy` skill's "Tabulka hypotez" (# / Typ /
Teze / Vstup / Cile / Invalidace) and its sizing rule (section 6: A+
confluence = full risk, clean A = half size, weaker = pass). Unlike the
skill -- which lays out the full A/B long/short table from a static
screenshot for a trader to choose from -- this reads one live snapshot, so
it only ever produces the single setup consistent with the *current*
regime, not all four types at once.

- A-day: VWAP mean reversion toward the intraday VWAP tier (the skill's
  "current decision level"). Direction comes from which side of the
  intraday VWAP price sits on; regime.py already requires the *overall*
  tier bias to be neutral for A_DAY, so this is the only directional
  signal available.
- B-day: momentum continuation in the direction of acceptance beyond the
  monthly/weekly VWAP tiers. regime.py already requires a non-neutral
  structural bias for B_DAY, so bullish/bearish is unambiguous here.

Unlike regime.py/delta.py, nothing here introduces new unvalidated numeric
thresholds -- entry/targets/invalidation are all read directly off
existing VWAP levels and active composite zones, not fabricated
constants. The regime classification feeding this still needs the
calibration flagged in regime.py/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from ..bridge.csv_bridge import LiveMarketState
from ..composite.models import Composite
from .delta import DeltaSignal
from .regime import Regime
from .tiers import Position, StructuralBias, TierReport


class HypothesisType(Enum):
    A_LONG = "A long"
    A_SHORT = "A short"
    B_LONG = "B long"
    B_SHORT = "B short"


class Confluence(Enum):
    A_PLUS = "a_plus"  # full risk
    CLEAN = "clean"  # half size
    WEAK = "weak"  # pass


@dataclass(frozen=True)
class Hypothesis:
    type: HypothesisType
    thesis: str
    entry: float
    target_1: Optional[float]
    target_2: Optional[float]
    runner: Optional[float]
    invalidation: float
    confluence: Confluence

    @property
    def is_primary(self) -> bool:
        return self.confluence == Confluence.A_PLUS


def _composite_targets(composites: Sequence[Composite], price: float, long: bool) -> List[float]:
    """Active composite edges on the trade's target side, nearest first --
    val above price for a long, vah below price for a short. Only the edge
    closer to price is used per composite; that's the level price actually
    has to clear to reach the zone.
    """
    edges = []
    for c in composites:
        if not c.is_active:
            continue
        if long and c.val > price:
            edges.append(c.val)
        elif not long and c.vah < price:
            edges.append(c.vah)
    edges.sort(key=lambda edge: abs(edge - price))
    return edges


def _strongest_composite_target(composites: Sequence[Composite], price: float, long: bool) -> Optional[float]:
    candidates = [
        (c.day_count, c.val if long else c.vah)
        for c in composites
        if c.is_active and ((long and c.val > price) or (not long and c.vah < price))
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda c: -c[0])
    return candidates[0][1]


def _opposing_invalidation(composites: Sequence[Composite], price: float, long: bool, fallback: float) -> float:
    """Nearest active composite edge on the side that would negate the
    trade -- below entry for a long, above for a short. Falls back to
    ``fallback`` (a VWAP level) when no such zone exists.
    """
    opposing = _composite_targets(composites, price, long=not long)
    return opposing[0] if opposing else fallback


def _confluence(delta_supports: bool, delta_contradicts: bool, has_target: bool) -> Confluence:
    if delta_contradicts:
        return Confluence.WEAK
    if delta_supports and has_target:
        return Confluence.A_PLUS
    return Confluence.CLEAN


def generate_hypothesis(
    state: LiveMarketState,
    regime: Regime,
    tier_report: TierReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite] = (),
) -> Optional[Hypothesis]:
    if regime == Regime.A_DAY:
        return _a_day_hypothesis(state, tier_report, delta_signal, composites)
    if regime == Regime.B_DAY:
        return _b_day_hypothesis(state, tier_report, delta_signal, composites)
    return None


def _a_day_hypothesis(
    state: LiveMarketState,
    tier_report: TierReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite],
) -> Optional[Hypothesis]:
    if tier_report.intraday == Position.AT:
        return None  # sitting at the mean already -- nothing to revert from
    long = tier_report.intraday == Position.BELOW
    hyp_type = HypothesisType.A_LONG if long else HypothesisType.A_SHORT

    # Absorption/divergence at the tested extreme argues the move away from
    # VWAP is exhausting -- supports reversion. Delta confirming that move
    # argues against reversion (real conviction behind it, not a bounce).
    delta_supports = delta_signal in (DeltaSignal.ABSORPTION, DeltaSignal.DIVERGENCE)
    delta_contradicts = delta_signal == DeltaSignal.CONFIRMING

    targets = _composite_targets(composites, state.last_price, long)
    target_1 = targets[0] if targets else state.vwap_intraday
    target_2 = targets[1] if len(targets) > 1 else None
    runner = _strongest_composite_target(composites, state.last_price, long)
    invalidation = _opposing_invalidation(composites, state.last_price, long, fallback=state.session_open)

    thesis = (
        f"Price {'below' if long else 'above'} intraday VWAP on a range day -- "
        f"expect reversion toward intraday VWAP ({state.vwap_intraday:.2f})."
    )

    return Hypothesis(
        type=hyp_type,
        thesis=thesis,
        entry=state.last_price,
        target_1=target_1,
        target_2=target_2,
        runner=runner,
        invalidation=invalidation,
        confluence=_confluence(delta_supports, delta_contradicts, bool(targets)),
    )


def _b_day_hypothesis(
    state: LiveMarketState,
    tier_report: TierReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite],
) -> Optional[Hypothesis]:
    if tier_report.structural_bias == StructuralBias.NEUTRAL:
        return None  # defensive only -- regime.classify_regime already rules this out for B_DAY
    long = tier_report.structural_bias == StructuralBias.BULLISH
    hyp_type = HypothesisType.B_LONG if long else HypothesisType.B_SHORT

    delta_supports = delta_signal == DeltaSignal.CONFIRMING
    delta_contradicts = delta_signal in (DeltaSignal.DIVERGENCE, DeltaSignal.ABSORPTION)

    targets = _composite_targets(composites, state.last_price, long)
    target_1 = targets[0] if targets else None
    target_2 = targets[1] if len(targets) > 1 else None
    runner = _strongest_composite_target(composites, state.last_price, long)
    # The immediate level that would lose the acceptance-beyond-VWAP read.
    invalidation = state.vwap_intraday

    thesis = (
        f"Price accepted {'above' if long else 'below'} the monthly/weekly VWAP "
        f"with {'confirming' if delta_supports else 'unconfirmed'} delta -- "
        "momentum continuation."
    )

    return Hypothesis(
        type=hyp_type,
        thesis=thesis,
        entry=state.last_price,
        target_1=target_1,
        target_2=target_2,
        runner=runner,
        invalidation=invalidation,
        confluence=_confluence(delta_supports, delta_contradicts, bool(targets)),
    )
