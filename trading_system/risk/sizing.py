"""Position sizing: confluence + entry/invalidation -> a number of contracts.

Mirrors the `trading-vwap-hypotezy` skill's section 6 sizing rule (A+
confluence = full risk, clean A = half size, weaker = pass). Three sizing
strategies are supported -- which one is "correct" depends on the account,
not something to guess, so all three are implemented rather than picking one:

- FIXED_CONTRACTS: a flat contract count per confluence tier, set directly.
- PERCENT_RISK: a % of account equity converted to contracts via the
  instrument's real tick size/value (e.g. NQ: tick_size=0.25,
  tick_value=5.0) -- these are real contract specs, not guessed
  thresholds like regime.py's.
- FIXED_RISK_USD: a flat dollar-risk budget per confluence tier (e.g. $500
  for A+, $250 for clean), added at the user's request so sizing doesn't
  need an account_equity figure at all -- just "how many dollars am I
  willing to risk on this trade". Shares PERCENT_RISK's per-contract-dollar
  math (via tick_size/tick_value) and its "round down, 0 if too small"
  behavior; only how the dollar budget itself is derived differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..hypothesis.generator import Confluence


class SizingMode(Enum):
    FIXED_CONTRACTS = "fixed_contracts"
    PERCENT_RISK = "percent_risk"
    FIXED_RISK_USD = "fixed_risk_usd"


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

    # FIXED_RISK_USD
    full_risk_usd: float = 0.0  # e.g. 500.0 = risk up to $500 on an A+ trade
    half_risk_usd: float = 0.0  # e.g. 250.0 for a clean/half-size trade

    # Shared by PERCENT_RISK and FIXED_RISK_USD to convert a price distance
    # into dollars; unused by FIXED_CONTRACTS.
    tick_size: float = 0.0
    tick_value: float = 0.0


def _dollar_risk_per_contract(entry: float, invalidation: float, config: SizingConfig) -> Optional[float]:
    """None when there's no real price distance or tick spec to convert it
    with -- callers treat that the same as "can't size this," i.e. 0 contracts.
    """
    risk_per_contract_price = abs(entry - invalidation)
    if risk_per_contract_price <= 0 or config.tick_size <= 0:
        return None
    risk_per_contract_dollars = (risk_per_contract_price / config.tick_size) * config.tick_value
    return risk_per_contract_dollars if risk_per_contract_dollars > 0 else None


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

    risk_per_contract_dollars = _dollar_risk_per_contract(entry, invalidation, config)
    if risk_per_contract_dollars is None:
        return 0

    if config.mode == SizingMode.FIXED_RISK_USD:
        dollar_budget = config.full_risk_usd if confluence == Confluence.A_PLUS else config.half_risk_usd
    else:  # PERCENT_RISK
        fraction = config.full_risk_fraction if confluence == Confluence.A_PLUS else config.half_risk_fraction
        dollar_budget = config.account_equity * fraction

    return int(dollar_budget // risk_per_contract_dollars)
