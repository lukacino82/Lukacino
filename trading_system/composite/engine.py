"""Sequential engine that turns a stream of daily profiles into composites.

Feed it one :class:`DailyProfile` at a time, in chronological order, per
instrument (historical replay or live end-of-day close). It merges
consecutive overlapping days into extending-rectangle composites and
invalidates older composites once a newer one eats into their range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from .models import Composite, DailyProfile
from .overlap import intersection, overlap_fraction, range_overlap_fraction

DEFAULT_MERGE_THRESHOLD_PCT = 60.0
DEFAULT_INVALIDATE_THRESHOLD_PCT = 10.0


def _composite_id(composite: Composite) -> str:
    return f"{composite.instrument}#{composite.start_date.isoformat()}"


def _remainder_ranges(
    old_low: float, old_high: float, new_low: float, new_high: float
) -> Tuple[Tuple[float, float], ...]:
    """Part(s) of the old range not covered by the new range."""
    inter = intersection(old_low, old_high, new_low, new_high)
    if inter is None:
        return ((old_low, old_high),)
    lo, hi = inter
    segments: List[Tuple[float, float]] = []
    if old_low < lo:
        segments.append((old_low, lo))
    if hi < old_high:
        segments.append((hi, old_high))
    return tuple(segments)


@dataclass
class CompositeEngine:
    merge_threshold_pct: float = DEFAULT_MERGE_THRESHOLD_PCT
    invalidate_threshold_pct: float = DEFAULT_INVALIDATE_THRESHOLD_PCT

    composites: List[Composite] = field(default_factory=list)
    _last_profile: Dict[str, DailyProfile] = field(default_factory=dict)
    _pending_day: Dict[str, DailyProfile] = field(default_factory=dict)
    _active_composite: Dict[str, Composite] = field(default_factory=dict)

    def ingest_day(self, profile: DailyProfile) -> Optional[Composite]:
        """Process one day's profile. Returns the composite it affected, if any."""
        instrument = profile.instrument
        prev_profile = self._last_profile.get(instrument)
        active_composite = self._active_composite.get(instrument)
        result: Optional[Composite] = None

        if prev_profile is not None:
            overlap_pct = overlap_fraction(prev_profile, profile)
            merges = overlap_pct >= self.merge_threshold_pct
        else:
            merges = False

        if merges and active_composite is not None:
            active_composite.extend(profile)
            result = active_composite
        elif merges:
            # Invariant: whenever a chain isn't already active, the previous
            # ingest must have gone through the "else" branch below and
            # seeded `_pending_day`, so it is always present here.
            pending = self._pending_day.pop(instrument)
            composite = Composite(
                instrument=instrument,
                start_date=pending.session_date,
                end_date=profile.session_date,
                val=min(pending.val, profile.val),
                vah=max(pending.vah, profile.vah),
                day_count=2,
                member_dates=(pending.session_date, profile.session_date),
            )
            self.composites.append(composite)
            self._active_composite[instrument] = composite
            result = composite
        else:
            self._active_composite.pop(instrument, None)
            self._pending_day[instrument] = profile

        if result is not None:
            self._invalidate_older_composites(result)

        self._last_profile[instrument] = profile
        return result

    def _invalidate_older_composites(self, current: Composite) -> None:
        current_id = _composite_id(current)
        for other in self.composites:
            if other is current or other.instrument != current.instrument:
                continue
            if not other.is_active or other.end_date > current.end_date:
                continue
            overlap_pct = range_overlap_fraction(other.val, other.vah, current.val, current.vah)
            if overlap_pct >= self.invalidate_threshold_pct:
                remaining = _remainder_ranges(other.val, other.vah, current.val, current.vah)
                other.invalidate(by_id=current_id, on=current.end_date, remaining_ranges=remaining)

    def active_composites(self, instrument: Optional[str] = None) -> List[Composite]:
        return [
            c
            for c in self.composites
            if c.is_active and (instrument is None or c.instrument == instrument)
        ]
