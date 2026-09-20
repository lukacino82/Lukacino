"""An OrderProposal: what SEMI_AUTO shows the trader to confirm by hand.

Builds on hypothesis.generator.Hypothesis + risk.sizing -- this only ever
computes a proposal, it never places anything. Real order placement (DTC,
FULLY_AUTO) is separate and later, per ARCHITECTURE.md's "Operating modes".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..hypothesis.generator import Confluence, Hypothesis, HypothesisType
from .sizing import SizingConfig, calculate_contracts

_LONG_TYPES = (HypothesisType.A_LONG, HypothesisType.B_LONG, HypothesisType.COUNTER_LONG)


@dataclass(frozen=True)
class OrderProposal:
    instrument: str
    hypothesis_type: HypothesisType
    direction: str  # "long" or "short"
    entry: float
    stop: float
    target_1: Optional[float]
    target_2: Optional[float]
    runner: Optional[float]
    contracts: int
    confluence: Confluence
    # How `contracts` splits across scale-out legs (decided with the user:
    # split by confluence, not evenly regardless of it) -- see
    # _split_contracts_by_confluence's docstring. Always sums to `contracts`.
    # ACSIL places one bracket order per nonzero leg, all sharing `stop`; no
    # separate stop management (breakeven-on-fill, trailing) yet -- that's
    # FULLY_AUTO-era work, deferred the same way pyramiding/trailing are.
    contracts_target1: int
    contracts_target2: int
    contracts_runner: int


def _split_evenly(total: int, n_legs: int) -> List[int]:
    """Splits `total` into `n_legs` whole-number parts, largest-first --
    e.g. (4, 3) -> [2, 1, 1], (1, 3) -> [1, 0, 0]. The first leg (target_1)
    getting any remainder/the only contract when legs can't all be funded is
    deliberate: target_1 is the closest, most-likely-to-fill level, so it's
    the one a too-small size should never be dropped from.
    """
    if n_legs <= 0:
        return []
    base, remainder = divmod(total, n_legs)
    return [base + (1 if i < remainder else 0) for i in range(n_legs)]


def _split_contracts_by_confluence(
    confluence: Confluence,
    total_contracts: int,
    target_2: Optional[float],
    runner: Optional[float],
) -> tuple:
    """Decides how many scale-out legs to use and splits `total_contracts`
    across them -- the user's explicit choice over an even 1/3 split
    regardless of confluence: A+ scales out across target_1/target_2/runner
    (three legs), Clean only across target_1/runner (two legs, no
    target_2 leg), and anything else (WEAK never reaches here -- it's
    filtered out before this by contracts <= 0) is a single target_1 leg,
    same as before this feature existed.

    A leg is dropped (folded back into target_1) whenever its confluence
    tier calls for it but the hypothesis has no price for it (target_2/
    runner is None) or the total is too small to fund every desired leg --
    see _split_evenly. Returns (contracts_target1, contracts_target2,
    contracts_runner), always summing to total_contracts.
    """
    legs = ["target_1"]
    if confluence == Confluence.A_PLUS:
        if target_2 is not None:
            legs.append("target_2")
        if runner is not None:
            legs.append("runner")
    elif confluence == Confluence.CLEAN:
        if runner is not None:
            legs.append("runner")

    amounts = dict(zip(legs, _split_evenly(total_contracts, len(legs))))
    return amounts.get("target_1", 0), amounts.get("target_2", 0), amounts.get("runner", 0)


def build_order_proposal(
    instrument: str,
    hypothesis: Optional[Hypothesis],
    config: SizingConfig,
) -> Optional[OrderProposal]:
    """None when there's no hypothesis, confluence is WEAK (pass), or the
    sized contract count rounds down to 0.
    """
    if hypothesis is None:
        return None
    contracts = calculate_contracts(hypothesis.confluence, hypothesis.entry, hypothesis.invalidation, config)
    if contracts <= 0:
        return None
    contracts_target1, contracts_target2, contracts_runner = _split_contracts_by_confluence(
        hypothesis.confluence, contracts, hypothesis.target_2, hypothesis.runner
    )
    return OrderProposal(
        instrument=instrument,
        hypothesis_type=hypothesis.type,
        direction="long" if hypothesis.type in _LONG_TYPES else "short",
        entry=hypothesis.entry,
        stop=hypothesis.invalidation,
        target_1=hypothesis.target_1,
        target_2=hypothesis.target_2,
        runner=hypothesis.runner,
        contracts=contracts,
        confluence=hypothesis.confluence,
        contracts_target1=contracts_target1,
        contracts_target2=contracts_target2,
        contracts_runner=contracts_runner,
    )
