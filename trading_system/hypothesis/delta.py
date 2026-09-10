"""Cumulative-delta absorption/divergence reading over a rolling window.

From the `trading-vwap-hypotezy` skill: "hledej absorpci a divergence (silna
delta bez posunu ceny = absorpce; nove cenove extremy bez potvrzeni delty =
divergence)". This compares the oldest and newest `LiveMarketState` snapshot
in a rolling window (fed one snapshot at a time as `live_state.csv` refreshes)
the same way the skill reads a delta bar against its price bar.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Sequence

from ..bridge.csv_bridge import LiveMarketState


class DeltaSignal(Enum):
    ABSORPTION = "absorption"
    DIVERGENCE = "divergence"
    CONFIRMING = "confirming"
    NEUTRAL = "neutral"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class DeltaSample:
    price: float
    cum_delta: float


def classify_delta(
    samples: Sequence[DeltaSample],
    price_move_threshold: float,
    delta_move_threshold: float,
) -> DeltaSignal:
    if len(samples) < 2:
        return DeltaSignal.INSUFFICIENT_DATA

    price_move = samples[-1].price - samples[0].price
    delta_move = samples[-1].cum_delta - samples[0].cum_delta
    price_moved = abs(price_move) >= price_move_threshold
    delta_moved = abs(delta_move) >= delta_move_threshold

    if delta_moved and not price_moved:
        return DeltaSignal.ABSORPTION
    if price_moved and not delta_moved:
        return DeltaSignal.DIVERGENCE
    if price_moved and delta_moved:
        # Delta pushing the opposite way from price is also a divergence --
        # the skill's "new price extreme without delta confirmation" case
        # extended to cover delta actively disagreeing, not just staying flat.
        same_direction = (price_move > 0) == (delta_move > 0)
        return DeltaSignal.CONFIRMING if same_direction else DeltaSignal.DIVERGENCE
    return DeltaSignal.NEUTRAL


class DeltaHistory:
    """Accumulates `LiveMarketState` snapshots as they arrive and classifies
    the resulting rolling window. `maxlen` bounds memory for a long-running
    process reading `live_state.csv` on every refresh.
    """

    def __init__(self, maxlen: int = 20) -> None:
        self._samples: Deque[DeltaSample] = deque(maxlen=maxlen)

    def add(self, state: LiveMarketState) -> None:
        self._samples.append(DeltaSample(price=state.last_price, cum_delta=state.cum_delta))

    def __len__(self) -> int:
        return len(self._samples)

    def classify(self, price_move_threshold: float, delta_move_threshold: float) -> DeltaSignal:
        return classify_delta(self._samples, price_move_threshold, delta_move_threshold)
