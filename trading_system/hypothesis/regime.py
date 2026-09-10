"""A-day (range/balance) vs. B-day (trend/imbalance) session regime.

From the `trading-vwap-hypotezy` skill:
- A-day: "open uvnitr vcerejsi value, maly gap, balancovana delta, cena mezi
  tiery" (open inside yesterday's value area, small gap, balanced delta,
  price between the VWAP tiers).
- B-day: "gap ven z VA, jednostranna delta, akceptace mimo mesicni/tydenni
  VWAP" (gap outside yesterday's value area, one-sided delta, acceptance
  outside the monthly/weekly VWAP).

The thresholds below (``gap_threshold_fraction``, ``delta_imbalance``) are
best-effort defaults, not calibrated numbers -- exactly like the composite
merge/invalidation percentages in ARCHITECTURE.md, they need checking
against real chart examples per instrument (NQ's typical cumulative delta
magnitude is nothing like, say, EURUSD's) before this is trusted for a real
hypothesis. Pass instrument-specific values once you have them instead of
relying on the defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..composite.models import DailyProfile
from .tiers import StructuralBias, TierReport


class Regime(Enum):
    A_DAY = "a_day"
    B_DAY = "b_day"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class RegimeInputs:
    session_open: float
    yesterday: DailyProfile
    tier_report: TierReport
    cum_delta: float


def _gap_outside_value(session_open: float, yesterday: DailyProfile) -> float:
    """Distance of ``session_open`` outside yesterday's value area; 0.0 if inside."""
    if session_open < yesterday.val:
        return yesterday.val - session_open
    if session_open > yesterday.vah:
        return session_open - yesterday.vah
    return 0.0


def classify_regime(
    inputs: RegimeInputs,
    gap_threshold_fraction: float = 0.25,
    delta_imbalance: float = 1000.0,
) -> Regime:
    """``gap_threshold_fraction`` is of yesterday's value-area range (val-vah);
    a gap beyond that fraction outside the value area counts as a "real" gap.
    ``delta_imbalance`` is an absolute cum_delta magnitude beyond which delta
    counts as one-sided rather than balanced -- both need calibration, see
    module docstring.
    """
    yesterday_range = inputs.yesterday.vah - inputs.yesterday.val
    gap = _gap_outside_value(inputs.session_open, inputs.yesterday)
    small_gap = gap == 0.0 or (yesterday_range > 0 and gap <= gap_threshold_fraction * yesterday_range)
    balanced_delta = abs(inputs.cum_delta) <= delta_imbalance
    price_between_tiers = inputs.tier_report.structural_bias == StructuralBias.NEUTRAL

    # All three signs must agree -- one B-day sign alone (e.g. a real gap
    # with otherwise balanced delta and price between tiers) is a mixed
    # read, not a clean B-day, so it's left UNCLEAR rather than forced into
    # either bucket.
    if small_gap and balanced_delta and price_between_tiers:
        return Regime.A_DAY
    if not small_gap and not balanced_delta and not price_between_tiers:
        return Regime.B_DAY
    return Regime.UNCLEAR
