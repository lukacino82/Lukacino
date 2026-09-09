from datetime import date

from trading_system.composite.models import DailyProfile
from trading_system.composite.overlap import overlap_fraction, range_overlap_fraction


def test_range_overlap_fraction_is_percentage_of_smaller_range():
    # intersection [104,110] = 6, smaller range = 10 -> 60%
    assert range_overlap_fraction(100, 110, 104, 114) == 60.0


def test_range_overlap_fraction_zero_when_disjoint():
    assert range_overlap_fraction(100, 110, 120, 130) == 0.0


def test_overlap_fraction_falls_back_to_range_without_histograms():
    a = DailyProfile("ES", date(2024, 1, 1), val=100, vah=110, poc=105)
    b = DailyProfile("ES", date(2024, 1, 2), val=104, vah=114, poc=108)
    assert overlap_fraction(a, b) == 60.0


def test_overlap_fraction_uses_volume_histogram_when_available():
    # Value areas overlap 60% by price range, but almost all of A's volume
    # actually sits outside the shared band -> transaction overlap is low.
    a = DailyProfile(
        "ES",
        date(2024, 1, 1),
        val=100,
        vah=110,
        poc=101,
        volume_at_price={101: 90, 109: 10},
    )
    b = DailyProfile(
        "ES",
        date(2024, 1, 2),
        val=104,
        vah=114,
        poc=113,
        volume_at_price={105: 10, 113: 90},
    )
    # shared band is [104,110]; only 10 of A's 100 contracts (10%) traded
    # there, so the transaction overlap must be far below the 60% that a
    # pure price-range comparison would report.
    assert overlap_fraction(a, b) == 10.0
