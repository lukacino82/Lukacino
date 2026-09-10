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
        """All three tiers agreeing reads as a runaway trend; anything mixed
        is the "decision zone at the edge" case the skill's bias table
        describes, and is intentionally read as neutral rather than guessed.
        """
        positions = (self.monthly, self.weekly, self.intraday)
        if all(p == Position.ABOVE for p in positions):
            return StructuralBias.BULLISH
        if all(p == Position.BELOW for p in positions):
            return StructuralBias.BEARISH
        return StructuralBias.NEUTRAL


def tier_report(state: LiveMarketState, tolerance: float = 0.0) -> TierReport:
    return TierReport(
        monthly=classify_position(state.last_price, state.vwap_monthly, tolerance),
        weekly=classify_position(state.last_price, state.vwap_weekly, tolerance),
        intraday=classify_position(state.last_price, state.vwap_intraday, tolerance),
    )
