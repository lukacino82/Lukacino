from trading_system.hypothesis.generator import Confluence, Hypothesis, HypothesisType
from trading_system.risk.order import build_order_proposal
from trading_system.risk.sizing import SizingConfig, SizingMode, calculate_contracts


def _hypothesis(
    hyp_type: HypothesisType = HypothesisType.A_LONG,
    confluence: Confluence = Confluence.A_PLUS,
    entry: float = 100.0,
    invalidation: float = 99.0,
) -> Hypothesis:
    return Hypothesis(
        type=hyp_type,
        thesis="test",
        entry=entry,
        target_1=105.0,
        target_2=None,
        runner=None,
        invalidation=invalidation,
        confluence=confluence,
    )


def test_calculate_contracts_weak_confluence_is_always_zero():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    assert calculate_contracts(Confluence.WEAK, 100.0, 99.0, config) == 0


def test_fixed_contracts_mode_uses_full_or_half_count():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    assert calculate_contracts(Confluence.A_PLUS, 100.0, 99.0, config) == 2
    assert calculate_contracts(Confluence.CLEAN, 100.0, 99.0, config) == 1


def test_percent_risk_mode_converts_dollar_budget_to_contracts():
    # NQ-like specs: tick_size=0.25, tick_value=5.0 -> $20/point risk.
    # entry-invalidation = 1.0 point -> $20 risk per contract.
    # 1% of $50,000 = $500 budget -> 25 contracts.
    config = SizingConfig(
        mode=SizingMode.PERCENT_RISK,
        account_equity=50_000.0,
        full_risk_fraction=0.01,
        half_risk_fraction=0.005,
        tick_size=0.25,
        tick_value=5.0,
    )
    assert calculate_contracts(Confluence.A_PLUS, 100.0, 99.0, config) == 25
    assert calculate_contracts(Confluence.CLEAN, 100.0, 99.0, config) == 12  # 0.5% -> $250 / $20 = 12.5 -> 12


def test_percent_risk_mode_rounds_down_to_zero_when_budget_too_small():
    config = SizingConfig(
        mode=SizingMode.PERCENT_RISK,
        account_equity=1_000.0,
        full_risk_fraction=0.001,
        half_risk_fraction=0.0005,
        tick_size=0.25,
        tick_value=5.0,
    )
    assert calculate_contracts(Confluence.A_PLUS, 100.0, 99.0, config) == 0


def test_percent_risk_mode_zero_when_invalidation_equals_entry():
    config = SizingConfig(
        mode=SizingMode.PERCENT_RISK,
        account_equity=50_000.0,
        full_risk_fraction=0.01,
        half_risk_fraction=0.005,
        tick_size=0.25,
        tick_value=5.0,
    )
    assert calculate_contracts(Confluence.A_PLUS, 100.0, 100.0, config) == 0


def test_build_order_proposal_none_when_no_hypothesis():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    assert build_order_proposal("NQ", None, config) is None


def test_build_order_proposal_none_when_weak_confluence():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    hyp = _hypothesis(confluence=Confluence.WEAK)
    assert build_order_proposal("NQ", hyp, config) is None


def test_build_order_proposal_long_direction_and_sizing():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    hyp = _hypothesis(hyp_type=HypothesisType.A_LONG, confluence=Confluence.A_PLUS, entry=100.0, invalidation=99.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert proposal is not None
    assert proposal.instrument == "NQ"
    assert proposal.direction == "long"
    assert proposal.entry == 100.0
    assert proposal.stop == 99.0
    assert proposal.contracts == 2
    assert proposal.confluence == Confluence.A_PLUS


def test_build_order_proposal_short_direction():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    hyp = _hypothesis(hyp_type=HypothesisType.B_SHORT, confluence=Confluence.CLEAN, entry=100.0, invalidation=101.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert proposal.direction == "short"
    assert proposal.contracts == 1
