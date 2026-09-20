"""A-day (range/balance) vs. B-day (trend/imbalance) session regime.

From the `trading-vwap-hypotezy` skill: VWAP tier bias (MM/monthly, HF/weekly,
intraday) plus cumulative delta, read the same way a trader watches them live
through the session -- A-day is a balanced, range-bound read (delta balanced,
price sitting between the tiers, i.e. neutral structural bias); B-day is
acceptance beyond the tiers confirmed by one-sided delta pushing the *same*
direction as that bias.

Originally this also gated on the session-open gap vs. yesterday's value area
(the skill's "gap ven z VA" sign -- easy to read off a single static morning
screenshot). Dropped after a real Replay-mode test on live NQ data: a
multi-hour, clearly one-directional session never classified as B_DAY because
it never opened with a large gap, even though the tier bias and delta were
one-sided the entire way -- exactly what a trader watching it live (not just
a morning screenshot) would call a trend day. Continuous real data is this
system's actual advantage over the skill's screenshot-only view, so leaning
on tier bias/delta directly instead of a same-gap proxy is more faithful to
the skill's intent, not less. This also means a regime read no longer needs
yesterday's DailyProfile at all -- a hypothesis can fire from the very first
live tick of a fresh instrument, before any daily_profile_export.csv row has
ever been written.

`delta_imbalance` (an absolute cum_delta magnitude beyond which delta counts
as one-sided rather than balanced) is a best-effort default, not a calibrated
number -- like the composite merge/invalidation percentages in
ARCHITECTURE.md, it needs checking against real chart examples per instrument
(NQ's typical cumulative delta magnitude is nothing like, say, EURUSD's)
before this is trusted for a real hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .tiers import StructuralBias, TierReport


class Regime(Enum):
    A_DAY = "a_day"
    B_DAY = "b_day"
    UNCLEAR = "unclear"
    # From hypothesis/synthesis.py's classify_counter_intraday -- MM/HF bias
    # opposed by the current intraday read, confirmed by delta absorption/
    # divergence at that extreme (ARCHITECTURE.md item 8). Never produced by
    # classify_regime below; LiveEngine.tick() sets this directly when the
    # synthesis model's trigger fires, ahead of the A/B-day check.
    COUNTER_INTRADAY = "counter_intraday"


@dataclass(frozen=True)
class RegimeInputs:
    tier_report: TierReport
    cum_delta: float


def classify_regime(inputs: RegimeInputs, delta_imbalance: float = 1000.0) -> Regime:
    """Returns UNCLEAR unless delta and tier bias clearly agree on the same
    read -- one balanced/neutral pair for A_DAY, or one one-sided-delta/
    non-neutral-bias pair pushing the *same* direction for B_DAY. A one-sided
    delta fighting a non-neutral bias (e.g. price accepted above the tiers
    while delta is one-sided selling) is a divergence, not a confirmed trend,
    so it's left UNCLEAR rather than forced into B_DAY just because both
    signs happen to be non-neutral.
    """
    balanced_delta = abs(inputs.cum_delta) <= delta_imbalance
    bias = inputs.tier_report.structural_bias

    if balanced_delta and bias == StructuralBias.NEUTRAL:
        return Regime.A_DAY
    if not balanced_delta and bias != StructuralBias.NEUTRAL:
        delta_bullish = inputs.cum_delta > 0
        bias_bullish = bias == StructuralBias.BULLISH
        if delta_bullish == bias_bullish:
            return Regime.B_DAY
    return Regime.UNCLEAR
