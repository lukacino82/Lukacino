"""VWAP tier position and structural-bias classification.

See the `trading-vwap-hypotezy` skill and ARCHITECTURE.md ("Goal") for the
underlying methodology: monthly VWAP (MM / money managers) and weekly VWAP
(HF / hedge funds) set the structural bias, intraday VWAP is where execution
happens. The skill's screenshots also show a +-2 standard deviation band
around each closed period's VWAP (the colored "VWAP schranka" rectangles) --
that band isn't exposed over ACSIL/the bridge yet (see ARCHITECTURE.md), so
this only classifies position relative to the three VWAP centerlines in
`LiveMarketState`, not the full band.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..bridge.csv_bridge import LiveMarketState


class Position(Enum):
    ABOVE = "above"
    AT = "at"
    BELOW = "below"


class StructuralBias(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


def classify_position(price: float, vwap: float, tolerance: float = 0.0) -> Position:
    """``tolerance`` is an absolute price distance counted as "at" the VWAP."""
    diff = price - vwap
    if abs(diff) <= tolerance:
        return Position.AT
    return Position.ABOVE if diff > 0 else Position.BELOW


@dataclass(frozen=True)
class TierReport:
    monthly: Position
    weekly: Position
    intraday: Position

    @property
    def structural_bias(self) -> StructuralBias:
        """A majority (2 of the 3) tiers agreeing is enough for a directional
        read; only a genuine three-way split (no side reaching 2) is neutral.

        Originally required all three to agree, on the theory that anything
        mixed was the skill's "decision zone at the edge" case and should be
        read as neutral rather than guessed. Loosened after real Replay-mode
        testing (and cross-checking the actual Notion "Daily Hypotheses"
        methodology, which commits to one HTF Bias per instrument/day, not a
        three-way unanimous vote) showed unanimous-3 essentially never
        happens in practice: monthly and weekly VWAP move slowly across a
        session while intraday price oscillates around its own VWAP
        constantly, so intraday alone flipping the "wrong" way for a few
        ticks -- even during a real, persistent trend the slower monthly/
        weekly tiers already confirm -- forced bias back to NEUTRAL and
        starved B_DAY of almost every signal it should have gotten. Two of
        three agreeing is still a real majority read, not a guess.
        """
        positions = (self.monthly, self.weekly, self.intraday)
        above = sum(1 for p in positions if p == Position.ABOVE)
        below = sum(1 for p in positions if p == Position.BELOW)
        if above >= 2:
            return StructuralBias.BULLISH
        if below >= 2:
            return StructuralBias.BEARISH
        return StructuralBias.NEUTRAL


def tier_report(state: LiveMarketState, tolerance: float = 0.0) -> TierReport:
    return TierReport(
        monthly=classify_position(state.last_price, state.vwap_monthly, tolerance),
        weekly=classify_position(state.last_price, state.vwap_weekly, tolerance),
        intraday=classify_position(state.last_price, state.vwap_intraday, tolerance),
    )
