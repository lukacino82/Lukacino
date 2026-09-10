"""Position sizing: confluence + entry/invalidation -> a number of contracts.

Mirrors the `trading-vwap-hypotezy` skill's section 6 sizing rule (A+
confluence = full risk, clean A = half size, weaker = pass). Two sizing
strategies are supported -- which one is "correct" depends on the account,
not something to guess, so both are implemented rather than picking one:

- FIXED_CONTRACTS: a flat contract count per confluence tier, set directly.
- PERCENT_RISK: a % of account equity converted to contracts via the
  instrument's real tick size/value (e.g. NQ: tick_size=0.25,
  tick_value=5.0) -- these are real contract specs, not guessed
  thresholds like regime.py's.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..hypothesis.generator import Confluence


class SizingMode(Enum):
    FIXED_CONTRACTS = "fixed_contracts"
    PERCENT_RISK = "percent_risk"


@dataclass(frozen=True)
class SizingConfig:
    mode: SizingMode

    # FIXED_CONTRACTS
    full_risk_contracts: int = 0
    half_risk_contracts: int = 0

    # PERCENT_RISK
    account_equity: float = 0.0
    full_risk_fraction: float = 0.0  # e.g. 0.01 = 1% of equity
    half_risk_fraction: float = 0.0  # e.g. 0.005 = 0.5% of equity
    tick_size: float = 0.0
    tick_value: float = 0.0


def calculate_contracts(
    confluence: Confluence,
    entry: float,
    invalidation: float,
    config: SizingConfig,
) -> int:
    """0 for WEAK confluence (the skill's "pass"), or when the computed
    size rounds down to nothing (invalidation too far for the risk budget).
    """
    if confluence == Confluence.WEAK:
        return 0

    if config.mode == SizingMode.FIXED_CONTRACTS:
        return config.full_risk_contracts if confluence == Confluence.A_PLUS else config.half_risk_contracts

    # PERCENT_RISK
    risk_per_contract_price = abs(entry - invalidation)
    if risk_per_contract_price <= 0 or config.tick_size <= 0:
        return 0
    risk_per_contract_dollars = (risk_per_contract_price / config.tick_size) * config.tick_value
    if risk_per_contract_dollars <= 0:
        return 0
    fraction = config.full_risk_fraction if confluence == Confluence.A_PLUS else config.half_risk_fraction
    dollar_budget = config.account_equity * fraction
    return int(dollar_budget // risk_per_contract_dollars)
