"""Formats a Hypothesis + OrderProposal as the text body ACSIL draws.

Reuses the existing bridge.csv_bridge.write_hypothesis()/hypothesis.txt
pipe (ACSIL already reads that file and draws its contents in a text
drawing -- see TradingHypothesisStudy.cpp "4. Draw the hypothesis text
box") rather than adding a new file format or touching the ACSIL side at
all: this is the fastest path to a SEMI_AUTO proposal actually appearing
on the chart.
"""

from __future__ import annotations

from typing import Optional

from ..risk.order import OrderProposal
from .generator import Hypothesis


def format_hypothesis_text(hypothesis: Hypothesis, proposal: Optional[OrderProposal]) -> str:
    lines = [
        f"{hypothesis.type.value} -- {hypothesis.confluence.value.upper()}",
        hypothesis.thesis,
        f"Entry: {hypothesis.entry:.2f}   Invalidation: {hypothesis.invalidation:.2f}",
    ]

    target_parts = []
    if hypothesis.target_1 is not None:
        target_parts.append(f"T1 {hypothesis.target_1:.2f}")
    if hypothesis.target_2 is not None:
        target_parts.append(f"T2 {hypothesis.target_2:.2f}")
    if hypothesis.runner is not None and hypothesis.runner not in (hypothesis.target_1, hypothesis.target_2):
        target_parts.append(f"Runner {hypothesis.runner:.2f}")
    if target_parts:
        lines.append("Targets: " + " / ".join(target_parts))
    else:
        lines.append("Targets: none active nearby")

    if proposal is not None:
        lines.append(f"Proposed size: {proposal.contracts} contracts ({proposal.direction})")
    else:
        lines.append("Proposed size: pass (weak confluence or size rounds to 0)")

    return "\n".join(lines)
