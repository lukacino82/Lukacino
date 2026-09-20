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

Target candidates come from two structural sources, both read directly off
active composites (no fabricated constants): the composite's own val/vah
edges (``_composite_targets``) and each member day's individual POC
(``_poc_targets``) -- POC is a distinct key level price tends to retest on
its own, not just the composite's merged value-area boundary. The two are
merged and sorted by distance from price (``_structural_targets``) to pick
target_1/target_2 when no fixed RRR is configured; ``runner`` stays keyed to
the single strongest (highest day_count) composite edge specifically, per
the skill's "biggest zone is the stretch target" reading.

``rrr`` (optional, e.g. 1.5 for a 1.5:1 reward:risk) is a user-configured
override for target_1 only, added at the user's request so target_1 can be
a plain multiple of the stop distance instead of always depending on
composite/POC structure existing at all: ``target_1 = entry +/- rrr *
abs(entry - invalidation)``. When RRR is set, target_2 becomes the nearest
structural candidate that sits *beyond* the RRR-derived target_1 in the
trade's direction (so it's still a real second level to scale into, not one
already passed). ``runner`` is unaffected either way. Applies identically
to SEMI_AUTO and FULLY_AUTO, since both read whatever this writes to
order_proposal.csv -- no ACSIL-side change needed for this.

``fixed_risk_distance`` (optional, a price distance already converted from
whatever unit the user configured it in -- points/ticks or a USD amount --
by run_live.py/run_backtest.py's InstrumentConfig, since only they know the
instrument's tick_size/tick_value) is a second, independent override: when
set, ``invalidation`` is always ``entry -/+ fixed_risk_distance`` instead of
the structural composite/VWAP-derived stop. Added after a real Replay-mode
run picked an ancient, price-irrelevant composite edge as a stop (price had
moved thousands of points away from it without a newer composite ever
overlapping and invalidating it) -- composites only expire via that ≥10%
overlap rule, never just because price ran away from them, so a structural
stop can silently become nonsense. A fixed distance is immune to that: it's
always a sane, predictable distance from entry, at the cost of no longer
reacting to real structure. It composes with ``rrr`` for free -- RRR's
``abs(entry - invalidation)`` risk figure is whatever this override made
``invalidation`` -- and with sizing.calculate_contracts' PERCENT_RISK/
FIXED_RISK_USD modes the same way, since both already work off
``abs(entry - invalidation)`` too. Leaving it ``None`` (the default) keeps
the original structural-stop behavior, including the wrong-side safety
check below.

The regime classification feeding this still needs the calibration flagged
in regime.py/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from ..bridge.csv_bridge import LiveMarketState
from ..composite.models import Composite
from .delta import DeltaSignal
from .regime import Regime
from .synthesis import HTFBiasReport, HTFConviction
from .tiers import Position, StructuralBias, TierReport


class HypothesisType(Enum):
    A_LONG = "A long"
    A_SHORT = "A short"
    B_LONG = "B long"
    B_SHORT = "B short"
    COUNTER_LONG = "Counter long"
    COUNTER_SHORT = "Counter short"


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


def _poc_targets(composites: Sequence[Composite], price: float, long: bool) -> List[float]:
    """Each active composite's member days' individual POC levels that sit
    on the trade's target side, nearest first -- POC is a distinct key
    level price tends to retest on its own, not just the composite's merged
    value-area edge (which _composite_targets already covers).
    """
    levels = [
        poc
        for c in composites
        if c.is_active
        for poc in c.member_pocs
        if ((poc > price) if long else (poc < price))
    ]
    levels.sort(key=lambda lvl: abs(lvl - price))
    return levels


def _structural_targets(composites: Sequence[Composite], price: float, long: bool) -> List[float]:
    """Composite value-area edges and member POCs merged into one
    nearest-first candidate list -- the pool target_1/target_2 are picked
    from when no fixed RRR is configured (see module docstring).
    """
    merged = _composite_targets(composites, price, long) + _poc_targets(composites, price, long)
    merged.sort(key=lambda lvl: abs(lvl - price))
    return merged


def _beyond(levels: Sequence[float], price: float, long: bool) -> List[float]:
    """Filters an already nearest-first candidate list down to levels that
    sit strictly beyond ``price`` (an RRR-derived target_1) in the trade's
    direction -- used so target_2 is still a real further level to scale
    into, not one the RRR target has already passed.
    """
    return [lvl for lvl in levels if ((lvl > price) if long else (lvl < price))]


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


def _rrr_target(entry: float, invalidation: float, rrr: float, long: bool) -> float:
    risk = abs(entry - invalidation)
    return entry + rrr * risk if long else entry - rrr * risk


def _pick_targets(
    structural_targets: Sequence[float],
    entry: float,
    invalidation: float,
    long: bool,
    rrr: Optional[float],
    no_structural_fallback: Optional[float],
) -> "tuple[Optional[float], Optional[float]]":
    """Returns (target_1, target_2). When ``rrr`` is set, target_1 is a
    plain multiple of the stop distance (see module docstring) and target_2
    is the nearest structural candidate that sits *beyond* it in the
    trade's direction. Otherwise both come straight from
    ``structural_targets``, with target_1 falling back to
    ``no_structural_fallback`` when there's no structural candidate at all
    (A-day passes ``vwap_intraday``; B-day passes ``None``, its existing
    "no target" case).
    """
    if rrr is not None:
        target_1 = _rrr_target(entry, invalidation, rrr, long)
        beyond = _beyond(structural_targets, target_1, long)
        target_2 = beyond[0] if beyond else None
        return target_1, target_2

    target_1 = structural_targets[0] if structural_targets else no_structural_fallback
    target_2 = structural_targets[1] if len(structural_targets) > 1 else None
    return target_1, target_2


def _fixed_invalidation(entry: float, long: bool, fixed_risk_distance: float) -> float:
    return entry - fixed_risk_distance if long else entry + fixed_risk_distance


def generate_hypothesis(
    state: LiveMarketState,
    regime: Regime,
    tier_report: TierReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite] = (),
    rrr: Optional[float] = None,
    fixed_risk_distance: Optional[float] = None,
) -> Optional[Hypothesis]:
    if regime == Regime.A_DAY:
        return _a_day_hypothesis(state, tier_report, delta_signal, composites, rrr, fixed_risk_distance)
    if regime == Regime.B_DAY:
        return _b_day_hypothesis(state, tier_report, delta_signal, composites, rrr, fixed_risk_distance)
    return None


def _a_day_hypothesis(
    state: LiveMarketState,
    tier_report: TierReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite],
    rrr: Optional[float] = None,
    fixed_risk_distance: Optional[float] = None,
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

    structural_targets = _structural_targets(composites, state.last_price, long)
    runner = _strongest_composite_target(composites, state.last_price, long)

    if fixed_risk_distance is not None:
        invalidation = _fixed_invalidation(state.last_price, long, fixed_risk_distance)
    else:
        invalidation = _opposing_invalidation(composites, state.last_price, long, fallback=state.session_open)

        # The session_open fallback (only used when no composite gives a real
        # invalidation level) is nothing but the day's opening print -- there's
        # no guarantee it sits on the correct side of entry. A real live run
        # showed it doesn't always: price can already have moved past the
        # session open in either direction before this hypothesis fires,
        # putting the "invalidation" on the WRONG side of both entry and the
        # target (a short with its stop below the target it's aiming at).
        # Proposing a trade with a backwards risk level is worse than proposing
        # none -- same principle as B-day's missing-target_1 case below. Moot
        # with a fixed_risk_distance, which is always on the correct side by
        # construction.
        if (long and invalidation >= state.last_price) or (not long and invalidation <= state.last_price):
            return None

    target_1, target_2 = _pick_targets(
        structural_targets, state.last_price, invalidation, long, rrr,
        no_structural_fallback=state.vwap_intraday,
    )

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
        confluence=_confluence(delta_supports, delta_contradicts, bool(structural_targets)),
    )


def _counter_confluence(conviction: HTFConviction, has_target: bool) -> Confluence:
    """HTF conviction (see synthesis.py) drives sizing here, not delta
    agreement/contradiction like `_confluence` above -- delta absorption/
    divergence at the intraday extreme is already required just to reach
    this function at all (classify_counter_intraday's trigger condition),
    so there's no separate "delta contradicts" case to score down for.
    """
    if conviction == HTFConviction.LOW:
        return Confluence.WEAK
    if conviction == HTFConviction.HIGH and has_target:
        return Confluence.A_PLUS
    return Confluence.CLEAN


def generate_counter_intraday_hypothesis(
    state: LiveMarketState,
    tier_report: TierReport,
    htf_bias: HTFBiasReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite] = (),
    rrr: Optional[float] = None,
    fixed_risk_distance: Optional[float] = None,
) -> Optional[Hypothesis]:
    """The hypothesis for `hypothesis/synthesis.py`'s COUNTER_INTRADAY
    trigger -- called directly by LiveEngine.tick() ahead of the regime.py/
    generate_hypothesis A/B-day path above, not dispatched through it (see
    engine.py). Direction comes from `htf_bias.direction` (MM alone, per
    synthesis.py), not from tier_report.structural_bias.
    """
    long = htf_bias.direction == StructuralBias.BULLISH
    hyp_type = HypothesisType.COUNTER_LONG if long else HypothesisType.COUNTER_SHORT

    structural_targets = _structural_targets(composites, state.last_price, long)
    runner = _strongest_composite_target(composites, state.last_price, long)

    if fixed_risk_distance is not None:
        invalidation = _fixed_invalidation(state.last_price, long, fixed_risk_distance)
    else:
        # Unlike A-day (which falls back to vwap_intraday) or B-day (which
        # falls back to a plain "no target_1" case), there's no VWAP-based
        # fallback that's safely on the correct side here: the whole
        # trigger condition requires price already past vwap_intraday, so
        # using it as a stop would put it on the WRONG side by
        # construction (the exact bug class A-day's own wrong-side check
        # exists to catch). With no opposing composite edge and no
        # fixed_risk_distance configured, there is no safe stop to
        # propose, so this returns None rather than guessing one.
        opposing = _composite_targets(composites, state.last_price, long=not long)
        if not opposing:
            return None
        invalidation = opposing[0]

    target_1, target_2 = _pick_targets(
        structural_targets, state.last_price, invalidation, long, rrr,
        no_structural_fallback=None,
    )

    thesis = (
        f"Monthly VWAP bias {'bullish' if long else 'bearish'} "
        f"({htf_bias.conviction.value} conviction, weekly "
        f"{tier_report.weekly.value}) while intraday shows a "
        f"{'selloff' if long else 'rally'} ({tier_report.intraday.value} its "
        f"own VWAP) with delta {delta_signal.value} at the extreme -- "
        "counter-intraday entry in the higher-timeframe direction."
    )

    return Hypothesis(
        type=hyp_type,
        thesis=thesis,
        entry=state.last_price,
        target_1=target_1,
        target_2=target_2,
        runner=runner,
        invalidation=invalidation,
        confluence=_counter_confluence(htf_bias.conviction, bool(structural_targets)),
    )


def _b_day_hypothesis(
    state: LiveMarketState,
    tier_report: TierReport,
    delta_signal: DeltaSignal,
    composites: Sequence[Composite],
    rrr: Optional[float] = None,
    fixed_risk_distance: Optional[float] = None,
) -> Optional[Hypothesis]:
    if tier_report.structural_bias == StructuralBias.NEUTRAL:
        return None  # defensive only -- regime.classify_regime already rules this out for B_DAY
    long = tier_report.structural_bias == StructuralBias.BULLISH
    hyp_type = HypothesisType.B_LONG if long else HypothesisType.B_SHORT

    delta_supports = delta_signal == DeltaSignal.CONFIRMING
    delta_contradicts = delta_signal in (DeltaSignal.DIVERGENCE, DeltaSignal.ABSORPTION)

    structural_targets = _structural_targets(composites, state.last_price, long)
    runner = _strongest_composite_target(composites, state.last_price, long)
    if fixed_risk_distance is not None:
        invalidation = _fixed_invalidation(state.last_price, long, fixed_risk_distance)
    else:
        # The immediate level that would lose the acceptance-beyond-VWAP read.
        invalidation = state.vwap_intraday

    # With no RRR configured and no active composite/POC, B-day has no
    # target_1 at all -- an unopposed continuation call, deliberately left
    # without a fabricated target rather than guessing one (see
    # ARCHITECTURE.md/backtest's skipped_no_target). Setting `rrr` always
    # gives target_1 a value, since it no longer depends on structure
    # existing.
    target_1, target_2 = _pick_targets(
        structural_targets, state.last_price, invalidation, long, rrr,
        no_structural_fallback=None,
    )

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
        confluence=_confluence(delta_supports, delta_contradicts, bool(structural_targets)),
    )
