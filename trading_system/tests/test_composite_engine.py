from datetime import date, timedelta

from trading_system.composite.engine import CompositeEngine
from trading_system.composite.models import DailyProfile, Tier

INSTRUMENT = "ES"
D0 = date(2024, 1, 1)


def profile(day_offset: int, val: float, vah: float) -> DailyProfile:
    return DailyProfile(
        instrument=INSTRUMENT,
        session_date=D0 + timedelta(days=day_offset),
        val=val,
        vah=vah,
        poc=(val + vah) / 2,
    )


def test_single_day_never_forms_a_composite():
    engine = CompositeEngine()
    engine.ingest_day(profile(0, 100, 110))
    assert engine.composites == []


def test_overlap_at_or_above_threshold_merges_into_composite():
    engine = CompositeEngine()
    engine.ingest_day(profile(0, 100, 110))
    # intersection [104,110]=6, smaller range=10 -> exactly 60% (boundary, must merge)
    result = engine.ingest_day(profile(1, 104, 114))
    assert result is not None
    assert result.day_count == 2
    assert (result.val, result.vah) == (100, 114)
    assert result.tier == Tier.TIER_2_3


def test_overlap_below_threshold_does_not_merge():
    engine = CompositeEngine()
    engine.ingest_day(profile(0, 100, 110))
    # intersection [105.1,110]=4.9, smaller range=10 -> 49%, below threshold
    result = engine.ingest_day(profile(1, 105.1, 115.1))
    assert result is None
    assert engine.composites == []


def test_tier_progresses_from_2_3_to_4_to_5_plus_as_chain_extends():
    engine = CompositeEngine()
    # Each consecutive pair overlaps 80% (intersection 8 of range 10).
    ranges = [(100, 110), (102, 112), (104, 114), (106, 116), (108, 118)]
    result = None
    for i, (val, vah) in enumerate(ranges):
        result = engine.ingest_day(profile(i, val, vah))

    assert result.day_count == 5
    assert result.tier == Tier.TIER_5_PLUS
    assert (result.val, result.vah) == (100, 118)
    assert len(engine.composites) == 1

    # Confirm the tier actually changed along the way, not just at the end.
    engine2 = CompositeEngine()
    day_count_to_tier = {}
    for i, (val, vah) in enumerate(ranges):
        c = engine2.ingest_day(profile(i, val, vah))
        if c is not None:
            day_count_to_tier[c.day_count] = c.tier
    assert day_count_to_tier[2] == Tier.TIER_2_3
    assert day_count_to_tier[3] == Tier.TIER_2_3
    assert day_count_to_tier[4] == Tier.TIER_4
    assert day_count_to_tier[5] == Tier.TIER_5_PLUS


def test_non_overlapping_day_closes_chain_and_seeds_a_new_one():
    engine = CompositeEngine()
    engine.ingest_day(profile(0, 100, 110))
    engine.ingest_day(profile(1, 104, 114))  # merges -> composite day_count=2
    engine.ingest_day(profile(2, 300, 310))  # far away, no overlap -> closes chain

    assert len(engine.composites) == 1
    closed = engine.composites[0]
    assert closed.day_count == 2  # frozen, did not grow

    # A later overlapping day should start a brand-new composite, not reopen
    # the closed one.
    new_composite = engine.ingest_day(profile(3, 302, 312))
    assert new_composite is not None
    assert new_composite is not closed
    assert new_composite.day_count == 2
    assert len(engine.composites) == 2


def test_new_composite_invalidates_older_one_it_overlaps_by_ge_10_pct():
    engine = CompositeEngine()
    engine.ingest_day(profile(0, 100, 112))
    old = engine.ingest_day(profile(1, 104, 120))  # composite1: val=100, vah=120 (range 20)
    assert old.day_count == 2 and old.is_active

    # Gap day: does not overlap old composite's chain end, closes it.
    engine.ingest_day(profile(10, 115, 135))
    # New composite spans [115,140], overlapping old's top edge [115,120]=5,
    # which is 25% of old's 20-wide range -> well above the 10% threshold.
    new = engine.ingest_day(profile(11, 120, 140))

    assert old.invalidated_on is not None
    assert old.invalidated_by is not None
    assert old.remaining_ranges == ((100, 115),)
    assert new.is_active


def test_small_overlap_below_10_pct_does_not_invalidate():
    engine = CompositeEngine()
    engine.ingest_day(profile(0, 100, 112))
    old = engine.ingest_day(profile(1, 104, 120))  # composite1: [100,120], range 20

    engine.ingest_day(profile(10, 119, 140))
    # New composite spans [119,145]; overlap with old is [119,120]=1, which
    # is 1/20 = 5% of old's range -> below the 10% invalidation threshold.
    engine.ingest_day(profile(11, 125, 145))

    assert old.is_active
    assert old.invalidated_on is None
