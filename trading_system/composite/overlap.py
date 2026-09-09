"""Overlap-fraction calculations used for merging and invalidating composites.

Both merge (>=60%) and invalidation (>=10%) checks in the engine are plain
percentage thresholds against the functions here, so the thresholds stay in
one place (engine.py) and this module only answers "how much do these two
ranges/profiles overlap".
"""

from __future__ import annotations

from typing import Optional, Tuple

from .models import DailyProfile


def intersection(
    a_low: float, a_high: float, b_low: float, b_high: float
) -> Optional[Tuple[float, float]]:
    lo = max(a_low, b_low)
    hi = min(a_high, b_high)
    if lo >= hi:
        return None
    return lo, hi


def range_overlap_fraction(a_low: float, a_high: float, b_low: float, b_high: float) -> float:
    """Overlap as a percentage of the *smaller* of the two price ranges."""
    inter = intersection(a_low, a_high, b_low, b_high)
    if inter is None:
        return 0.0
    lo, hi = inter
    smaller_range = min(a_high - a_low, b_high - b_low)
    if smaller_range <= 0:
        return 0.0
    return min((hi - lo) / smaller_range, 1.0) * 100.0


def overlap_fraction(a: DailyProfile, b: DailyProfile) -> float:
    """Overlap as a percentage of "transactions", per the user's methodology.

    When both profiles carry a volume-at-price histogram, this is the volume
    of the *smaller* day's value area that falls inside the intersection of
    the two value-area ranges (i.e. "at least 60% of that day's transactions
    happened in the shared zone"). Without histograms it falls back to a
    plain price-range overlap of the two value areas.
    """
    if a.volume_at_price and b.volume_at_price:
        inter = intersection(a.val, a.vah, b.val, b.vah)
        if inter is None:
            return 0.0
        lo, hi = inter
        vol_a_va = a.value_area_volume
        vol_b_va = b.value_area_volume
        if not vol_a_va or not vol_b_va:
            return range_overlap_fraction(a.val, a.vah, b.val, b.vah)
        smaller = a if vol_a_va <= vol_b_va else b
        vol_in_intersection = sum(
            vol for price, vol in smaller.volume_at_price.items() if lo <= price <= hi
        )
        denom = min(vol_a_va, vol_b_va)
        return min(vol_in_intersection / denom, 1.0) * 100.0
    return range_overlap_fraction(a.val, a.vah, b.val, b.vah)
