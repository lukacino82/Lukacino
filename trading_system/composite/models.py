"""Data model for daily volume/market profiles and multi-day composites."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class DailyProfile:
    """One session's volume/market profile for one instrument.

    ``volume_at_price`` is the full price->volume histogram (e.g. from Sierra
    Chart's Volume-at-Price study) and is optional: when absent, overlap
    calculations fall back to a plain price-range comparison of the value
    area (val/vah).
    """

    instrument: str
    session_date: date
    val: float
    vah: float
    poc: float
    volume_at_price: Optional[Dict[float, float]] = None

    def __post_init__(self) -> None:
        if self.val > self.vah:
            raise ValueError(f"val ({self.val}) must be <= vah ({self.vah})")

    @property
    def value_area_volume(self) -> Optional[float]:
        if self.volume_at_price is None:
            return None
        return sum(
            vol for price, vol in self.volume_at_price.items() if self.val <= price <= self.vah
        )


class Tier(Enum):
    TIER_2_3 = "2-3D"
    TIER_4 = "4D"
    TIER_5_PLUS = "5D+"


# Color/transparency table as specified for the composite zones.
TIER_STYLE: Dict[Tier, Dict[str, object]] = {
    Tier.TIER_2_3: {"color": "light_pink", "fill_transparency": 75},
    Tier.TIER_4: {"color": "darker_pink", "fill_transparency": 45},
    Tier.TIER_5_PLUS: {"color": "darkest_pink", "fill_transparency": 20},
}


def classify_tier(day_count: int) -> Tier:
    if day_count < 2:
        raise ValueError("a composite requires at least 2 overlapping days")
    if day_count <= 3:
        return Tier.TIER_2_3
    if day_count == 4:
        return Tier.TIER_4
    return Tier.TIER_5_PLUS


@dataclass
class Composite:
    """A merged, multi-day 'extending rectangle' magnet zone."""

    instrument: str
    start_date: date
    end_date: date
    val: float
    vah: float
    day_count: int
    member_dates: Tuple[date, ...] = field(default_factory=tuple)
    invalidated_on: Optional[date] = None
    invalidated_by: Optional[str] = None
    remaining_ranges: Tuple[Tuple[float, float], ...] = field(default_factory=tuple)

    @property
    def tier(self) -> Tier:
        return classify_tier(self.day_count)

    @property
    def is_active(self) -> bool:
        return self.invalidated_on is None

    def extend(self, profile: DailyProfile) -> "Composite":
        """Grow this rectangle to also cover ``profile`` (mutates in place).

        The composite keeps a single stable identity as it extends day over
        day, which is what makes it an "extending rectangle" rather than a
        new zone each time a day is added.
        """
        self.end_date = profile.session_date
        self.val = min(self.val, profile.val)
        self.vah = max(self.vah, profile.vah)
        self.day_count += 1
        self.member_dates = self.member_dates + (profile.session_date,)
        return self

    def invalidate(self, by_id: str, on: date, remaining_ranges: Tuple[Tuple[float, float], ...]) -> None:
        self.invalidated_on = on
        self.invalidated_by = by_id
        self.remaining_ranges = remaining_ranges
