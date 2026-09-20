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
from typing import Deque, List, Optional, Sequence

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


class SessionDeltaPhase(Enum):
    """A session-long shape read over cumulative delta, distinct from
    DeltaHistory's short rolling window above (which stays exactly as-is --
    this doesn't replace it, it adds a second, longer-memory view).

    Needed for ARCHITECTURE.md item 8's second worked example: an
    early-session flush (delta strongly one-sided), a reset back toward
    zero by midday (inventory neutralizing, NOT itself a reversal), then a
    fresh leg as new participants arrive. A short rolling window alone
    can't tell a genuine reset apart from a genuine reversal, or a fresh
    renewed leg apart from noise around zero -- this tracks the whole
    session's arc instead.

    Deliberately a single FLAT->FLUSHING->RESET->RENEWED_* arc, not a
    repeating zigzag/swing detector -- that's exactly the shape the user
    described (one flush, one reset, one renewed leg), not a general
    multi-cycle oscillation tracker. RENEWED_DOWN/RENEWED_UP is terminal
    for the session once reached.
    """

    INSUFFICIENT_DATA = "insufficient_data"
    FLAT = "flat"  # never extended far enough from zero to call it a flush
    FLUSHING = "flushing"  # currently extending away from zero, no reset yet
    RESET = "reset"  # retraced back toward zero after a flush
    RENEWED_DOWN = "renewed_down"  # flush -> reset -> fresh leg down
    RENEWED_UP = "renewed_up"  # flush -> reset -> fresh leg up


@dataclass(frozen=True)
class SessionDeltaSample:
    cum_delta: float


@dataclass(frozen=True)
class SessionDeltaShape:
    phase: SessionDeltaPhase
    flush_extreme: Optional[float]  # the most extreme cum_delta before any reset; None until a flush is confirmed
    reset_value: Optional[float]  # cum_delta at the point a reset was confirmed; None until then
    current_delta: Optional[float]


def classify_session_delta_shape(
    samples: Sequence[SessionDeltaSample],
    flush_threshold: float,
    reset_retracement_threshold: float,
    renewal_threshold: float,
) -> SessionDeltaShape:
    """Pure function over an ordered (session-start to now) sample series --
    see SessionDeltaTracker below for the stateful, per-tick wrapper.

    All three thresholds are absolute cum_delta magnitudes (same convention
    as delta_move_threshold/delta_imbalance elsewhere in this package) and
    are placeholders, not calibrated numbers -- same caveat as every other
    threshold in this file/ARCHITECTURE.md.
    """
    if len(samples) < 2:
        return SessionDeltaShape(SessionDeltaPhase.INSUFFICIENT_DATA, None, None, None)

    flush_extreme = samples[0].cum_delta
    flush_confirmed = False
    reset_value: Optional[float] = None
    phase = SessionDeltaPhase.FLAT

    for sample in samples[1:]:
        d = sample.cum_delta

        if phase in (SessionDeltaPhase.FLAT, SessionDeltaPhase.FLUSHING):
            if abs(d) > abs(flush_extreme):
                flush_extreme = d
            if abs(flush_extreme) >= flush_threshold:
                flush_confirmed = True
                phase = SessionDeltaPhase.FLUSHING
                retraced = abs(flush_extreme - d)
                moving_toward_zero = abs(d) < abs(flush_extreme)
                if moving_toward_zero and retraced >= reset_retracement_threshold:
                    phase = SessionDeltaPhase.RESET
                    reset_value = d

        elif phase == SessionDeltaPhase.RESET:
            move_from_reset = d - reset_value
            if abs(move_from_reset) >= renewal_threshold:
                phase = SessionDeltaPhase.RENEWED_DOWN if move_from_reset < 0 else SessionDeltaPhase.RENEWED_UP
                # RENEWED_* is terminal for this pass -- see class docstring.
                break

    return SessionDeltaShape(
        phase=phase,
        flush_extreme=flush_extreme if flush_confirmed else None,
        reset_value=reset_value,
        current_delta=samples[-1].cum_delta,
    )


class SessionDeltaTracker:
    """Accumulates every LiveMarketState snapshot for the CURRENT trading
    session and classifies the resulting shape. Unlike DeltaHistory, this
    is unbounded (keeps the whole session, not a maxlen window) and must be
    reset at each new session boundary by the caller (LiveEngine keys this
    off LiveMarketState.session_open changing, the same per-session marker
    ACSIL already writes once per day).
    """

    def __init__(
        self,
        flush_threshold: float,
        reset_retracement_threshold: float,
        renewal_threshold: float,
    ) -> None:
        self._samples: List[SessionDeltaSample] = []
        self._flush_threshold = flush_threshold
        self._reset_retracement_threshold = reset_retracement_threshold
        self._renewal_threshold = renewal_threshold

    def add(self, state: LiveMarketState) -> None:
        self._samples.append(SessionDeltaSample(cum_delta=state.cum_delta))

    def reset(self) -> None:
        self._samples.clear()

    def shape(self) -> SessionDeltaShape:
        return classify_session_delta_shape(
            self._samples,
            self._flush_threshold,
            self._reset_retracement_threshold,
            self._renewal_threshold,
        )
