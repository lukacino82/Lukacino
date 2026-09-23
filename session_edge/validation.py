"""Kompletní validační protokol: backtest → nulové hypotézy → walk-forward."""
from __future__ import annotations

import itertools
from dataclasses import replace
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from . import stats
from .config import BacktestConfig
from .engine import prepare, random_direction, run_backtest, simulate
from .strategies import Strategy


def validate(
    data: pd.DataFrame,
    strategy: Strategy,
    cfg: BacktestConfig,
    n_trials: int = 1,
    n_random: int = 200,
    risk_per_trade: float = 0.01,
    seed: int = 0,
) -> dict:
    prepared = prepare(data, strategy, cfg)
    trades = simulate(prepared, cfg)
    report: dict = {"strategy": strategy.name, "params": strategy.params(),
                    "risk": cfg.risk.to_dict(), "summary": stats.summary(trades)}
    if len(trades) < 2:
        report["verdict"] = "Příliš málo obchodů."
        return report | {"trades": trades}

    r = trades["r"].to_numpy()
    report["bootstrap"] = stats.bootstrap_expectancy(r, seed=seed)
    null = np.array([
        simulate(prepared, cfg, direction_fn=random_direction, seed=seed + i + 1)["r"].mean()
        for i in range(n_random)
    ])
    report["random_direction"] = stats.random_direction_test(r.mean(), null)
    report["deflated_sharpe"] = stats.deflated_sharpe(r, n_trials=n_trials)
    report["min_trades_needed"] = stats.min_trades_for_significance(r.mean(), r.std(ddof=1))
    report["kelly"] = stats.kelly_fraction(r)
    report["monte_carlo"] = stats.monte_carlo_drawdown(r, risk_per_trade=risk_per_trade, seed=seed)
    report["by_year"] = stats.by_year(trades)
    report["verdict"] = verdict(report)
    report["trades"] = trades
    return report


def verdict(rep: dict) -> str:
    s = rep["summary"]
    checks = {
        "expectancy > 0 po nákladech": s["expectancy_r"] > 0,
        "t-stat > 2": s["t_stat"] > 2,
        "bootstrap 95% CI nad nulou": rep["bootstrap"]["ci_low"] > 0,
        "lepší než náhodný směr (p < 0.05)": rep["random_direction"]["p_value"] < 0.05,
        "Deflated Sharpe > 0.95": rep["deflated_sharpe"]["dsr"] > 0.95,
        "kladná většina let": (rep["by_year"]["expectancy_r"] > 0).mean() >= 0.6,
        ">= 100 obchodů": s["trades"] >= 100,
    }
    rep["checks"] = checks
    passed = sum(checks.values())
    if passed == len(checks):
        return f"KANDIDÁT NA HRANU ({passed}/{len(checks)}) – ověřte walk-forward a na jiném trhu."
    if passed >= len(checks) - 2:
        return f"SLIBNÉ, NEPROKÁZANÉ ({passed}/{len(checks)})."
    return f"BEZ PROKAZATELNÉ HRANY ({passed}/{len(checks)})."


def param_grid(**axes: Iterable) -> list[dict]:
    keys = list(axes)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(list(v) for v in axes.values()))]


def _apply(strategy: Strategy, cfg: BacktestConfig, params: dict) -> tuple[Strategy, BacktestConfig]:
    s_over = {k: v for k, v in params.items() if not k.startswith("risk.")}
    r_over = {k[5:]: v for k, v in params.items() if k.startswith("risk.")}
    strat = type(strategy)(**{**strategy.__dict__, **s_over}) if s_over else strategy
    new_cfg = replace(cfg, risk=replace(cfg.risk, **r_over)) if r_over else cfg
    return strat, new_cfg


def walk_forward(
    data: pd.DataFrame,
    strategy: Strategy,
    cfg: BacktestConfig,
    grid: list[dict],
    train_days: int = 500,
    test_days: int = 125,
    min_trades: int = 30,
    score: str = "t_stat",
) -> dict:
    """Rolling walk-forward: na tréninkovém okně vybere nejlepší parametry,
    použije je na následujícím (neviděném) okně. Výsledek = spojené OOS obchody,
    což je jediné poctivé číslo – parametry nikdy neviděly data, na kterých se měří."""
    local = data.tz_convert(strategy.tz)
    dates = np.array(sorted(set(local.index.date)))
    oos, log = [], []
    start = 0
    while start + train_days < len(dates):
        tr = dates[start: start + train_days]
        te = dates[start + train_days: start + train_days + test_days]
        # ATR potřebuje historii – testovací okno dostane i konec tréninku
        warm = dates[max(0, start + train_days - cfg.atr_days - 1)]
        d_train = local[(local.index.date >= tr[0]) & (local.index.date <= tr[-1])]
        d_test = local[(local.index.date >= warm) & (local.index.date <= te[-1])]

        best, best_score = None, -np.inf
        cache: dict = {}  # signály závisí jen na parametrech strategie, ne na risku
        for params in grid:
            s, c = _apply(strategy, cfg, params)
            key = repr(sorted((k, v) for k, v in params.items() if not k.startswith("risk.")))
            if key not in cache:
                cache[key] = prepare(d_train, s, c)
            t = simulate(cache[key], c)
            if len(t) < min_trades:
                continue
            sc = stats.summary(t)[score]
            if np.isfinite(sc) and sc > best_score:
                best, best_score = params, sc
        if best is not None:
            s, c = _apply(strategy, cfg, best)
            t = run_backtest(d_test, s, c)
            t = t[pd.to_datetime(t["date"]) >= pd.Timestamp(te[0])]
            oos.append(t)
            log.append({"test_from": te[0], "test_to": te[-1], "params": best,
                        "is_score": best_score, "oos_trades": len(t),
                        "oos_expectancy_r": t["r"].mean() if len(t) else np.nan})
        start += test_days

    oos_trades = pd.concat(oos, ignore_index=True) if oos else pd.DataFrame(columns=["r", "date"])
    return {"oos_trades": oos_trades, "windows": pd.DataFrame(log),
            "oos_summary": stats.summary(oos_trades) if len(oos_trades) else {"trades": 0},
            "n_trials": len(grid)}
