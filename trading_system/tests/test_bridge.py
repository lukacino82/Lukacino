from datetime import date, datetime

from trading_system.bridge.csv_bridge import (
    read_composites,
    read_daily_profiles,
    read_hypothesis,
    write_composites,
    write_daily_profiles,
    write_hypothesis,
)
from trading_system.composite.engine import CompositeEngine
from trading_system.composite.models import DailyProfile, Tier


def test_daily_profiles_round_trip(tmp_path):
    profiles = [
        DailyProfile("ES", date(2024, 1, 1), val=100, vah=110, poc=105),
        DailyProfile("GC", date(2024, 1, 2), val=2000, vah=2010, poc=2005),
    ]
    path = tmp_path / "daily_profile_export.csv"
    write_daily_profiles(path, profiles)
    result = read_daily_profiles(path)
    assert result == profiles


def test_active_composite_round_trip(tmp_path):
    engine = CompositeEngine()
    engine.ingest_day(DailyProfile("ES", date(2024, 1, 1), val=100, vah=110, poc=105))
    composite = engine.ingest_day(DailyProfile("ES", date(2024, 1, 2), val=104, vah=114, poc=108))

    path = tmp_path / "composites.csv"
    write_composites(path, engine.composites)
    result = read_composites(path)

    assert len(result) == 1
    restored = result[0]
    assert restored.instrument == composite.instrument
    assert restored.start_date == composite.start_date
    assert restored.end_date == composite.end_date
    assert (restored.val, restored.vah) == (composite.val, composite.vah)
    assert restored.day_count == composite.day_count
    assert restored.tier == Tier.TIER_2_3
    assert restored.is_active


def test_invalidated_composite_round_trip_keeps_remaining_ranges(tmp_path):
    engine = CompositeEngine()
    engine.ingest_day(DailyProfile("ES", date(2024, 1, 1), val=100, vah=112, poc=106))
    old = engine.ingest_day(DailyProfile("ES", date(2024, 1, 2), val=104, vah=120, poc=112))
    engine.ingest_day(DailyProfile("ES", date(2024, 1, 10), val=115, vah=135, poc=125))
    engine.ingest_day(DailyProfile("ES", date(2024, 1, 11), val=120, vah=140, poc=130))
    assert not old.is_active  # sanity check the scenario actually invalidates

    path = tmp_path / "composites.csv"
    write_composites(path, engine.composites)
    result = read_composites(path)

    restored_old = next(c for c in result if c.start_date == old.start_date)
    assert not restored_old.is_active
    assert restored_old.invalidated_on == old.invalidated_on
    assert restored_old.remaining_ranges == old.remaining_ranges


def test_hypothesis_round_trip(tmp_path):
    path = tmp_path / "hypothesis.txt"
    generated_at = datetime(2024, 1, 2, 7, 30)
    body = "HTF Bias: BEARISH\nRegime: B-day\n"
    write_hypothesis(path, "ES", generated_at, body)

    instrument, restored_time, restored_body = read_hypothesis(path)
    assert instrument == "ES"
    assert restored_time == generated_at
    assert restored_body == body
