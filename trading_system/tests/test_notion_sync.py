from datetime import date, datetime

from trading_system.bridge.csv_bridge import LiveMarketState
from trading_system.composite.models import Composite
from trading_system.hypothesis.delta import DeltaSignal
from trading_system.hypothesis.generator import Confluence, Hypothesis, HypothesisType
from trading_system.hypothesis.regime import Regime
from trading_system.hypothesis.tiers import Position, StructuralBias, TierReport
from trading_system.notion_sync.record import build_notion_record


def _state(last_price: float = 29639.0) -> LiveMarketState:
    return LiveMarketState(
        instrument="NQ",
        timestamp=datetime(2026, 9, 10, 14, 0, 0),
        last_price=last_price,
        session_open=29742.2,
        vwap_monthly=29678.3,
        vwap_weekly=29824.4,
        vwap_intraday=29676.4,
        cum_delta=66.0,
    )


_NEUTRAL_TIERS = TierReport(monthly=Position.ABOVE, weekly=Position.BELOW, intraday=Position.ABOVE)
_BEARISH_TIERS = TierReport(monthly=Position.BELOW, weekly=Position.BELOW, intraday=Position.BELOW)


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        type=HypothesisType.A_SHORT,
        thesis="test thesis",
        entry=29639.0,
        target_1=29676.4,
        target_2=None,
        runner=None,
        invalidation=29742.2,
        confluence=Confluence.CLEAN,
    )


def _composite(val: float, vah: float, day_count: int = 3) -> Composite:
    return Composite(instrument="NQ", start_date=date(2026, 9, 1), end_date=date(2026, 9, 5), val=val, vah=vah, day_count=day_count)


def test_title_and_date_from_timestamp():
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.UNCLEAR, DeltaSignal.NEUTRAL, None)
    assert record.title == "2026-09-10 -- NQ"
    assert record.date == date(2026, 9, 10)
    assert record.instrument == "NQ"


def test_htf_bias_and_regime_text():
    record = build_notion_record(_state(), _BEARISH_TIERS, Regime.B_DAY, DeltaSignal.CONFIRMING, None)
    assert record.htf_bias == "Bearish"
    assert record.regime == "B-den (trend)"


def test_primary_setup_none_when_no_hypothesis():
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.UNCLEAR, DeltaSignal.NEUTRAL, None)
    assert record.primary_setup is None


def test_primary_setup_matches_hypothesis_type_value():
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.A_DAY, DeltaSignal.NEUTRAL, _hypothesis())
    assert record.primary_setup == "A short"


def test_vwap_text_includes_position_and_diff():
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.UNCLEAR, DeltaSignal.NEUTRAL, None)
    assert "29678.30" in record.monthly_vwap_text
    assert "above" in record.monthly_vwap_text


def test_supply_and_demand_zones_from_active_composites():
    composites = [
        _composite(val=29700.0, vah=29750.0, day_count=4),  # above price -> supply
        _composite(val=29550.0, vah=29600.0, day_count=2),  # below price -> demand
    ]
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.UNCLEAR, DeltaSignal.NEUTRAL, None, composites)
    assert "29700.00-29750.00" in record.supply_zones_text
    assert "4D" in record.supply_zones_text
    assert "29550.00-29600.00" in record.demand_zones_text
    assert "2-3D" in record.demand_zones_text


def test_zone_text_none_active_nearby_when_no_composites():
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.UNCLEAR, DeltaSignal.NEUTRAL, None)
    assert record.supply_zones_text == "none active nearby"
    assert record.demand_zones_text == "none active nearby"


def test_delta_text_includes_value_and_signal():
    record = build_notion_record(_state(), _NEUTRAL_TIERS, Regime.UNCLEAR, DeltaSignal.ABSORPTION, None)
    assert "66" in record.delta_text
    assert "absorption" in record.delta_text
