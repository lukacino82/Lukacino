from datetime import date, datetime

from trading_system.bridge.csv_bridge import (
    LiveMarketState,
    OrderProposalSnapshot,
    append_live_state,
    read_composites,
    read_daily_profiles,
    read_hypothesis,
    read_live_state,
    read_live_state_history,
    read_order_proposal,
    write_composites,
    write_daily_profiles,
    write_hypothesis,
    write_live_state,
    write_order_proposal,
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


def test_daily_profiles_keeps_last_row_when_a_date_is_duplicated(tmp_path):
    """Reproduces a real run: two conflicting rows for the same date ended
    up in daily_profile_export.csv (see ARCHITECTURE.md). The last one
    written should win, not the first -- otherwise a stale/degenerate
    early export could permanently shadow a later, corrected one.
    """
    path = tmp_path / "daily_profile_export.csv"
    path.write_text(
        "date,instrument,val,vah,poc\n"
        "2026-09-14,NQ,29432.2,29492,29460\n"
        "2026-09-14,NQ,29331.5,29478.8,29451.8\n"
        "2026-09-15,NQ,29286.8,29286.8,29286.8\n"
        "2026-09-15,NQ,29227.2,29341.8,29275\n"
        "2026-09-16,NQ,29281,29535,29466.8\n"
    )
    result = read_daily_profiles(path)
    assert [p.session_date for p in result] == [date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)]
    assert result[0] == DailyProfile("NQ", date(2026, 9, 14), val=29331.5, vah=29478.8, poc=29451.8)
    assert result[1] == DailyProfile("NQ", date(2026, 9, 15), val=29227.2, vah=29341.8, poc=29275)


def test_append_live_state_builds_a_history_read_back_in_order(tmp_path):
    path = tmp_path / "historical_intraday.csv"
    states = [
        LiveMarketState("NQ", datetime(2024, 1, 2, 9, 30), 101.0, 100.5, 95.0, 95.0, 103.0, 0.0),
        LiveMarketState("NQ", datetime(2024, 1, 2, 9, 31), 102.0, 100.5, 95.0, 95.0, 103.0, 10.0),
    ]
    for state in states:
        append_live_state(path, state)

    result = read_live_state_history(path)
    assert result == states
    # Only one header line -- append_live_state must not rewrite it on later calls.
    assert path.read_text().count("timestamp,instrument") == 1


def test_order_proposal_round_trip_actionable(tmp_path):
    path = tmp_path / "order_proposal.csv"
    snapshot = OrderProposalSnapshot(
        timestamp=datetime(2026, 9, 16, 19, 46, 50),
        instrument="NQ",
        direction="short",
        hypothesis_type="A short",
        confluence="clean",
        entry=29452.80,
        stop=29486.20,
        target_1=29419.80,
        target_2=None,
        runner=None,
        contracts=1,
        contracts_target1=1,
        contracts_target2=0,
        contracts_runner=0,
    )
    write_order_proposal(path, snapshot)
    assert read_order_proposal(path) == snapshot


def test_order_proposal_round_trip_none_actionable(tmp_path):
    """When there's nothing tradeable, a row is still written (direction
    "none", contracts=0) so ACSIL can tell "checked, nothing to do" apart
    from "no file/stale file at all" -- see OrderProposalSnapshot's docstring.
    """
    path = tmp_path / "order_proposal.csv"
    snapshot = OrderProposalSnapshot(
        timestamp=datetime(2026, 9, 16, 19, 46, 50),
        instrument="NQ",
        direction="none",
        hypothesis_type="",
        confluence="",
        entry=None,
        stop=None,
        target_1=None,
        target_2=None,
        runner=None,
        contracts=0,
        contracts_target1=0,
        contracts_target2=0,
        contracts_runner=0,
    )
    write_order_proposal(path, snapshot)
    assert read_order_proposal(path) == snapshot


def test_read_order_proposal_returns_none_when_file_has_no_data_row(tmp_path):
    path = tmp_path / "order_proposal.csv"
    path.write_text(
        "timestamp,instrument,direction,hypothesis_type,confluence,entry,stop,target_1,target_2,runner,"
        "contracts,contracts_target1,contracts_target2,contracts_runner\n"
    )
    assert read_order_proposal(path) is None


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


def test_live_state_round_trip(tmp_path):
    path = tmp_path / "live_state.csv"
    state = LiveMarketState(
        instrument="ES",
        timestamp=datetime(2024, 1, 2, 14, 30, 5),
        last_price=4801.25,
        session_open=4790.0,
        vwap_monthly=4795.5,
        vwap_weekly=4802.75,
        vwap_intraday=4799.0,
        cum_delta=-1250.0,
    )
    write_live_state(path, state)
    assert read_live_state(path) == state


def test_live_state_overwritten_not_appended(tmp_path):
    path = tmp_path / "live_state.csv"
    first = LiveMarketState("ES", datetime(2024, 1, 2, 14, 30), 4801.25, 4790.0, 4795.5, 4802.75, 4799.0, -1250.0)
    second = LiveMarketState("ES", datetime(2024, 1, 2, 14, 30, 5), 4802.0, 4790.0, 4795.5, 4802.75, 4799.5, -1200.0)
    write_live_state(path, first)
    write_live_state(path, second)
    assert read_live_state(path) == second


def test_read_live_state_returns_none_when_only_header_written(tmp_path):
    path = tmp_path / "live_state.csv"
    path.write_text("timestamp,instrument,last_price,vwap_monthly,vwap_weekly,vwap_intraday,cum_delta\n")
    assert read_live_state(path) is None


def test_live_state_round_trip_includes_vwap_intraday_sd1(tmp_path):
    path = tmp_path / "live_state.csv"
    state = LiveMarketState(
        instrument="ES",
        timestamp=datetime(2024, 1, 2, 14, 30, 5),
        last_price=4801.25,
        session_open=4790.0,
        vwap_monthly=4795.5,
        vwap_weekly=4802.75,
        vwap_intraday=4799.0,
        cum_delta=-1250.0,
        vwap_intraday_sd1=12.5,
    )
    write_live_state(path, state)
    assert read_live_state(path) == state


def test_read_live_state_defaults_vwap_intraday_sd1_when_column_missing(tmp_path):
    """A historical_intraday.csv row logged before this field existed --
    read_live_state must fill in 0.0 ("not available"), not raise.
    """
    path = tmp_path / "live_state.csv"
    path.write_text(
        "timestamp,instrument,last_price,session_open,vwap_monthly,vwap_weekly,vwap_intraday,cum_delta\n"
        "2024-01-02T14:30:05,ES,4801.25,4790.0,4795.5,4802.75,4799.0,-1250.0\n"
    )
    state = read_live_state(path)
    assert state is not None
    assert state.vwap_intraday_sd1 == 0.0


def test_hypothesis_round_trip(tmp_path):
    path = tmp_path / "hypothesis.txt"
    generated_at = datetime(2024, 1, 2, 7, 30)
    body = "HTF Bias: BEARISH\nRegime: B-day\n"
    write_hypothesis(path, "ES", generated_at, body)

    instrument, restored_time, restored_body = read_hypothesis(path)
    assert instrument == "ES"
    assert restored_time == generated_at
    assert restored_body == body
