from trading_system.hypothesis.formatter import format_hypothesis_text
from trading_system.hypothesis.generator import Confluence, Hypothesis, HypothesisType
from trading_system.risk.order import OrderProposal


def _hypothesis(target_1=105.0, target_2=110.0, runner=110.0) -> Hypothesis:
    return Hypothesis(
        type=HypothesisType.A_LONG,
        thesis="Price below intraday VWAP -- expect reversion.",
        entry=100.0,
        target_1=target_1,
        target_2=target_2,
        runner=runner,
        invalidation=95.0,
        confluence=Confluence.A_PLUS,
    )


def _proposal(contracts=2, direction="long") -> OrderProposal:
    return OrderProposal(
        instrument="NQ",
        hypothesis_type=HypothesisType.A_LONG,
        direction=direction,
        entry=100.0,
        stop=95.0,
        target_1=105.0,
        target_2=110.0,
        runner=110.0,
        contracts=contracts,
        confluence=Confluence.A_PLUS,
    )


def test_includes_type_confluence_thesis_entry_invalidation():
    text = format_hypothesis_text(_hypothesis(), _proposal())
    assert "A long" in text
    assert "A_PLUS" in text
    assert "Price below intraday VWAP" in text
    assert "Entry: 100.00" in text
    assert "Invalidation: 95.00" in text


def test_lists_distinct_targets_only():
    text = format_hypothesis_text(_hypothesis(target_1=105.0, target_2=110.0, runner=110.0), _proposal())
    assert "T1 105.00" in text
    assert "T2 110.00" in text
    assert "Runner" not in text  # same as target_2, not repeated


def test_lists_runner_when_distinct_from_targets():
    text = format_hypothesis_text(_hypothesis(target_1=105.0, target_2=110.0, runner=120.0), _proposal())
    assert "Runner 120.00" in text


def test_no_targets_line_when_none_active():
    text = format_hypothesis_text(_hypothesis(target_1=None, target_2=None, runner=None), _proposal())
    assert "Targets: none active nearby" in text


def test_includes_proposed_size_and_direction():
    text = format_hypothesis_text(_hypothesis(), _proposal(contracts=3, direction="long"))
    assert "Proposed size: 3 contracts (long)" in text


def test_pass_text_when_no_proposal():
    text = format_hypothesis_text(_hypothesis(), None)
    assert "pass" in text.lower()
