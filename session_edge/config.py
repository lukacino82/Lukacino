"""Nastavení risk managementu a řízení obchodů.

Všechny parametry, které chce obchodník ladit ručně (TP/SL, RRR, max. počet
obchodů, čas nuceného uzavření), jsou soustředěny tady – strategie řeší jen
*kdy a kterým směrem* vstoupit, ne *kolik riskovat*.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import time
from typing import Literal, Optional

StopMode = Literal["strategy", "atr", "points", "range"]
TargetMode = Literal["rrr", "atr", "points", "none"]


def parse_time(value: Optional[str | time]) -> Optional[time]:
    """'15:55' -> time(15, 55). None zůstává None."""
    if value is None or isinstance(value, time):
        return value
    hh, mm = value.strip().split(":")[:2]
    return time(int(hh), int(mm))


@dataclass
class RiskConfig:
    """Parametry řízení obchodu.

    stop_mode
        strategy – stop, který navrhne strategie (např. opačná strana rangu)
        atr      – stop_value × denní ATR (počítané jen z minulých dní)
        points   – pevný stop v bodech / pipech ceny
        range    – stop_value × velikost referenčního rangu strategie
    target_mode
        rrr      – TP = riziko × rrr  (výchozí, RRR je hlavní páka)
        atr      – TP = target_value × denní ATR
        points   – pevný TP v bodech
        none     – bez TP, drží se do stopu / konce seance
    """

    stop_mode: StopMode = "strategy"
    stop_value: float = 1.0
    target_mode: TargetMode = "rrr"
    target_value: float = 0.0
    rrr: float = 2.0

    max_trades_per_day: int = 1
    # čas (v časové zóně strategie), kdy se otevřená pozice nuceně zavře;
    # None = zavřít na posledním baru dne v datech
    exit_time: Optional[time] = None
    # posun stopu na break-even po dosažení X R zisku (None = vypnuto)
    breakeven_at_r: Optional[float] = None
    # náklady na round-trip v cenových jednotkách (spread + poplatek + skluz)
    cost_per_trade: float = 0.0
    # minimální riziko v cenových jednotkách – chrání před nesmyslně malými stopy
    min_risk: float = 1e-9

    def __post_init__(self) -> None:
        self.exit_time = parse_time(self.exit_time)
        if self.max_trades_per_day < 1:
            raise ValueError("max_trades_per_day musí být >= 1")
        if self.target_mode == "rrr" and self.rrr <= 0:
            raise ValueError("rrr musí být > 0")
        if self.stop_mode != "strategy" and self.stop_value <= 0:
            raise ValueError("stop_value musí být > 0")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["exit_time"] = self.exit_time.strftime("%H:%M") if self.exit_time else None
        return d


@dataclass
class BacktestConfig:
    risk: RiskConfig = field(default_factory=RiskConfig)
    # počet předchozích dní pro výpočet denního ATR
    atr_days: int = 14
    # pokud entry bar zasáhne SL i TP, nevíme pořadí -> konzervativně SL
    conservative_intrabar: bool = True
