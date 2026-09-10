"""An OrderProposal: what SEMI_AUTO shows the trader to confirm by hand.

Builds on hypothesis.generator.Hypothesis + risk.sizing -- this only ever
computes a proposal, it never places anything. Real order placement (DTC,
FULLY_AUTO) is separate and later, per ARCHITECTURE.md's "Operating modes".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..hypothesis.generator import Confluence, Hypothesis, HypothesisType
from .sizing import SizingConfig, calculate_contracts

_LONG_TYPES = (HypothesisType.A_LONG, HypothesisType.B_LONG)


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
    )
