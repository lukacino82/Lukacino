"""Maps live engine output onto the trading-vwap-hypotezy skill's Notion schema.

Property names and select values are confirmed against the live Notion data
source (`53b58aaa-dfc2-4fbd-9b66-5a869047fffe`, "Trading denik -- hypotezy")
via notion-fetch, not just the skill's description text, so the manual
screenshot-driven path and this automated path write consistently. Notable
exact-match details confirmed this way: "HTF bias"'s neutral option is one
combined select value, "Neutral / Balance", not two separate ones; "Rezim"
uses "Nejasne" with its diacritic.

Open item, not something to guess past: the live Instrument select lists
ES/S&P500, Gold (XAUUSD), WTI Oil, GBP/USD, EUR/USD, USD/JPY, GBP/JPY --
NQ (Nasdaq futures) isn't among them. This passes the bridge's raw
instrument code through unchanged; a strict select property rejects a
value that isn't already one of its options, so writing a real NQ record
needs either an "NQ" option added to that select (ask before touching a
shared database) or a mapping decided some other way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from ..bridge.csv_bridge import LiveMarketState
from ..composite.models import Composite
from ..hypothesis.delta import DeltaSignal
from ..hypothesis.generator import Hypothesis
from ..hypothesis.regime import Regime
from ..hypothesis.tiers import StructuralBias, TierReport

_REGIME_TEXT = {
    Regime.A_DAY: "A-den (range)",
    Regime.B_DAY: "B-den (trend)",
    Regime.UNCLEAR: "Nejasné",
}

# Exact select option strings confirmed against the live Notion data source
# (53b58aaa-dfc2-4fbd-9b66-5a869047fffe) -- "Neutral / Balance" is one
# combined option there, not two separate ones.
_BIAS_TEXT = {
    StructuralBias.BULLISH: "Bullish",
    StructuralBias.BEARISH: "Bearish",
    StructuralBias.NEUTRAL: "Neutral / Balance",
}


@dataclass(frozen=True)
class NotionHypothesisRecord:
    title: str  # "Nazev": "YYYY-MM-DD -- <Instrument>"
    date: date  # "Datum"
    instrument: str  # "Instrument" -- see module docstring's open item
    htf_bias: str  # "HTF bias"
    regime: str  # "Rezim"
    primary_setup: Optional[str]  # "Primarni setup" -- None when no hypothesis
    monthly_vwap_text: str  # "MM mesicni VWAP"
    weekly_vwap_text: str  # "HF tydenni VWAP"
    intraday_vwap_text: str  # "Intraday denni VWAP"
    supply_zones_text: str  # "Supply zony"
    demand_zones_text: str  # "Demand zony"
    delta_text: str  # "Delta / order flow"


def _vwap_text(label: str, price: float, vwap: float, position) -> str:
    diff = price - vwap
    return f"{label} VWAP {vwap:.2f}, price {position.value} ({diff:+.2f})"


def _zone_text(composites: Sequence[Composite], price: float, above: bool) -> str:
    zones = []
    for c in composites:
        if not c.is_active:
            continue
        if above and c.val > price:
            zones.append(f"{c.val:.2f}-{c.vah:.2f} ({c.tier.value}, {c.day_count}d)")
        elif not above and c.vah < price:
            zones.append(f"{c.val:.2f}-{c.vah:.2f} ({c.tier.value}, {c.day_count}d)")
    if not zones:
        return "none active nearby"
    zones.sort(key=lambda text: text)
    return "; ".join(zones)


def _delta_text(cum_delta: float, signal: DeltaSignal) -> str:
    return f"Cumulative delta {cum_delta:.0f} ({signal.value})"


def build_notion_record(
    state: LiveMarketState,
    tier_report: TierReport,
    regime: Regime,
    delta_signal: DeltaSignal,
    hypothesis: Optional[Hypothesis],
    composites: Sequence[Composite] = (),
) -> NotionHypothesisRecord:
    session_date = state.timestamp.date()
    return NotionHypothesisRecord(
        title=f"{session_date.isoformat()} -- {state.instrument}",
        date=session_date,
        instrument=state.instrument,
        htf_bias=_BIAS_TEXT[tier_report.structural_bias],
        regime=_REGIME_TEXT[regime],
        primary_setup=hypothesis.type.value if hypothesis is not None else None,
        monthly_vwap_text=_vwap_text("Monthly", state.last_price, state.vwap_monthly, tier_report.monthly),
        weekly_vwap_text=_vwap_text("Weekly", state.last_price, state.vwap_weekly, tier_report.weekly),
        intraday_vwap_text=_vwap_text("Intraday", state.last_price, state.vwap_intraday, tier_report.intraday),
        supply_zones_text=_zone_text(composites, state.last_price, above=True),
        demand_zones_text=_zone_text(composites, state.last_price, above=False),
        delta_text=_delta_text(state.cum_delta, delta_signal),
    )
