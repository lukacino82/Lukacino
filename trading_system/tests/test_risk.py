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


def test_fixed_risk_usd_mode_converts_dollar_budget_to_contracts():
    # Same NQ-like specs/numbers as test_percent_risk_mode_converts_dollar_
    # budget_to_contracts, but the dollar budget is given directly instead
    # of as a fraction of account_equity.
    config = SizingConfig(
        mode=SizingMode.FIXED_RISK_USD,
        full_risk_usd=500.0,
        half_risk_usd=250.0,
        tick_size=0.25,
        tick_value=5.0,
    )
    assert calculate_contracts(Confluence.A_PLUS, 100.0, 99.0, config) == 25
    assert calculate_contracts(Confluence.CLEAN, 100.0, 99.0, config) == 12  # $250 / $20 = 12.5 -> 12


def test_fixed_risk_usd_mode_rounds_down_to_zero_when_budget_too_small():
    config = SizingConfig(
        mode=SizingMode.FIXED_RISK_USD,
        full_risk_usd=10.0,
        half_risk_usd=5.0,
        tick_size=0.25,
        tick_value=5.0,
    )
    assert calculate_contracts(Confluence.A_PLUS, 100.0, 99.0, config) == 0


def test_fixed_risk_usd_mode_zero_when_invalidation_equals_entry():
    config = SizingConfig(
        mode=SizingMode.FIXED_RISK_USD,
        full_risk_usd=500.0,
        half_risk_usd=250.0,
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


def _hypothesis_with_targets(confluence, target_2, runner) -> Hypothesis:
    return Hypothesis(
        type=HypothesisType.A_LONG,
        thesis="test",
        entry=100.0,
        target_1=105.0,
        target_2=target_2,
        runner=runner,
        invalidation=99.0,
        confluence=confluence,
    )


def test_scale_out_split_a_plus_three_legs_evenly():
    # User's explicit decision: A+ scales out across target_1/target_2/
    # runner, not a flat target_1-only fill.
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=3, half_risk_contracts=1)
    hyp = _hypothesis_with_targets(Confluence.A_PLUS, target_2=110.0, runner=115.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (1, 1, 1)
    assert proposal.contracts_target1 + proposal.contracts_target2 + proposal.contracts_runner == proposal.contracts


def test_scale_out_split_a_plus_remainder_goes_to_target1():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=4, half_risk_contracts=1)
    hyp = _hypothesis_with_targets(Confluence.A_PLUS, target_2=110.0, runner=115.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (2, 1, 1)


def test_scale_out_split_a_plus_too_few_contracts_drops_runner_leg():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=1)
    hyp = _hypothesis_with_targets(Confluence.A_PLUS, target_2=110.0, runner=115.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (1, 1, 0)


def test_scale_out_split_a_plus_single_contract_is_target1_only():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=1, half_risk_contracts=1)
    hyp = _hypothesis_with_targets(Confluence.A_PLUS, target_2=110.0, runner=115.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (1, 0, 0)


def test_scale_out_split_a_plus_missing_target2_price_folds_into_two_legs():
    # Hypothesis has no target_2 price at all -- confluence still says A+,
    # but there's nothing to attach a target_2 leg's order to.
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=3, half_risk_contracts=1)
    hyp = _hypothesis_with_targets(Confluence.A_PLUS, target_2=None, runner=115.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (2, 0, 1)


def test_scale_out_split_clean_uses_target1_and_runner_only():
    # User's explicit decision: Clean scales out across target_1/runner,
    # deliberately no target_2 leg (unlike A+'s three-leg split).
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=3)
    hyp = _hypothesis_with_targets(Confluence.CLEAN, target_2=110.0, runner=115.0)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (2, 0, 1)


def test_scale_out_split_clean_no_runner_price_is_target1_only():
    config = SizingConfig(mode=SizingMode.FIXED_CONTRACTS, full_risk_contracts=2, half_risk_contracts=3)
    hyp = _hypothesis_with_targets(Confluence.CLEAN, target_2=110.0, runner=None)
    proposal = build_order_proposal("NQ", hyp, config)
    assert (proposal.contracts_target1, proposal.contracts_target2, proposal.contracts_runner) == (3, 0, 0)
