"""VWAP tier position and structural-bias classification.

See the `trading-vwap-hypotezy` skill and ARCHITECTURE.md ("Goal") for the
underlying methodology: monthly VWAP (MM / money managers) and weekly VWAP
(HF / hedge funds) set the structural bias, intraday VWAP is where execution
happens. The skill's screenshots also show a +-2 standard deviation band
around each closed period's VWAP (the colored "VWAP schranka" rectangles) --
``tier_report`` below now uses a fraction of each tier's own +-1 SD band
(``LiveMarketState.vwap_*_sd1``, added for hypothesis/synthesis.py's
multi-timeframe model) as that tolerance, once ACSIL supplies it.
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


def tier_report(state: LiveMarketState, tolerance_fraction: float = 0.1) -> TierReport:
    """``tolerance_fraction`` of each tier's own +-1 SD band width counts as
    "at" that VWAP, instead of requiring price to equal the VWAP line
    exactly (``classify_position``'s own default). Zero tolerance meant
    ``Position.AT`` was practically unreachable with real, continuous
    prices -- for ``TierReport.structural_bias`` that was already masked by
    its 2-of-3 majority rule (see that property's own docstring on the
    earlier, related fix), but ``classify_htf_bias`` (synthesis.py) compares
    the weekly and monthly tiers directly: with weekly VWAP naturally
    oscillating far more than the slower monthly line, weekly==monthly
    (``HTFConviction.HIGH``) and weekly==AT (``MODERATE``) were both rare,
    leaving almost every case as ``LOW`` -- which ``_counter_confluence``
    (generator.py) screens out as ``WEAK`` before a trade is ever
    considered. A real 18-year ES backtest surfaced this: 1.25M
    counter-intraday regime hits produced only 4 actual trades.

    Falls back to 0.0 (the old exact-equality behavior) for any tier whose
    SD1 field isn't available yet (0.0, the same "not supplied" convention
    LiveMarketState's own fields use) -- e.g. an ACSIL build that hasn't
    been rebuilt with the monthly/weekly SD1 inputs added for the
    synthesis model still behaves exactly as before. 0.1 (10% of the SD1
    band) is a placeholder, same "not calibrated against real data" caveat
    as every other threshold here -- it only needed to be non-zero to fix
    the unreachable-MODERATE/rare-HIGH problem above; the exact fraction
    still wants real-data tuning.
    """

    def tolerance(sd1_distance: float) -> float:
        # vwap_*_sd1 is already a distance (how far the +-1 SD band sits
        # from its VWAP centerline, straight from ACSIL -- see
        # LiveMarketState's own field docstring), not a price level, so no
        # vwap subtraction here.
        return sd1_distance * tolerance_fraction if sd1_distance > 0.0 else 0.0

    return TierReport(
        monthly=classify_position(state.last_price, state.vwap_monthly, tolerance(state.vwap_monthly_sd1)),
        weekly=classify_position(state.last_price, state.vwap_weekly, tolerance(state.vwap_weekly_sd1)),
        intraday=classify_position(state.last_price, state.vwap_intraday, tolerance(state.vwap_intraday_sd1)),
    )
