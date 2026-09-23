"""Statistika a validace hrany.

Otázka není „vydělal backtest?“, ale „je velmi nepravděpodobné, že by
stejný výsledek vznikl náhodou – i po započtení toho, kolik variant jsme
vyzkoušeli?“. Proto:

1. expectancy v R + t-statistika a p-hodnota,
2. bootstrap interval spolehlivosti expectancy,
3. test náhodného směru (stejné časy vstupu, stejný SL/TP, směr = hod mincí),
4. Deflated Sharpe Ratio (korekce na počet vyzkoušených variant),
5. Monte Carlo drawdownů a riziko krachu pro zvolené % riziko na obchod.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def breakeven_winrate(rrr: float) -> float:
    """Minimální win-rate, při které je systém s daným RRR na nule (bez nákladů)."""
    return 1.0 / (1.0 + rrr)


def summary(trades: pd.DataFrame) -> dict:
    r = trades["r"].to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {"trades": 0}
    wins, losses = r[r > 0], r[r <= 0]
    mean = r.mean()
    sd = r.std(ddof=1) if n > 1 else float("nan")
    t = mean / (sd / math.sqrt(n)) if n > 1 and sd > 0 else float("nan")
    equity = np.cumsum(r)
    dd = equity - np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = -losses.mean() if len(losses) else 0.0
    realized_rrr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    streak = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)

    days = trades["date"].nunique()
    span_days = (pd.Timestamp(trades["date"].max()) - pd.Timestamp(trades["date"].min())).days or 1
    trades_per_year = n / span_days * 365.25
    return {
        "trades": n,
        "days_traded": int(days),
        "win_rate": len(wins) / n,
        "avg_win_r": avg_win,
        "avg_loss_r": avg_loss,
        "realized_rrr": realized_rrr,
        "breakeven_win_rate": 1 / (1 + realized_rrr) if np.isfinite(realized_rrr) else 0.0,
        "expectancy_r": mean,
        "std_r": sd,
        "t_stat": t,
        "p_value": 1 - _N.cdf(t) if np.isfinite(t) else float("nan"),  # jednostranný
        "profit_factor": wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf"),
        "total_r": equity[-1],
        "max_drawdown_r": -dd.min() if len(dd) else 0.0,
        "max_losing_streak": streak,
        "sharpe_per_trade": mean / sd if sd and sd > 0 else float("nan"),
        "sharpe_annual": mean / sd * math.sqrt(trades_per_year) if sd and sd > 0 else float("nan"),
        "trades_per_year": trades_per_year,
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
    }


def bootstrap_expectancy(r: np.ndarray, n_boot: int = 10_000, ci: float = 0.95, seed: int = 0) -> dict:
    """Bootstrap intervalu spolehlivosti průměrného R a P(expectancy <= 0)."""
    r = np.asarray(r, dtype=float)
    rng = np.random.default_rng(seed)
    means = rng.choice(r, size=(n_boot, len(r)), replace=True).mean(axis=1)
    a = (1 - ci) / 2
    return {
        "mean": r.mean(),
        "ci_low": float(np.quantile(means, a)),
        "ci_high": float(np.quantile(means, 1 - a)),
        "prob_le_zero": float((means <= 0).mean()),
    }


def random_direction_test(
    real_expectancy: float, null_expectancies: np.ndarray
) -> dict:
    """p-hodnota: jak často dá náhodný směr stejně dobrou nebo lepší expectancy."""
    null = np.asarray(null_expectancies, dtype=float)
    p = (np.sum(null >= real_expectancy) + 1) / (len(null) + 1)
    return {
        "real": real_expectancy,
        "null_mean": float(null.mean()),
        "null_95pct": float(np.quantile(null, 0.95)),
        "p_value": float(p),
    }


def _moments(r: np.ndarray) -> tuple[float, float]:
    m, s = r.mean(), r.std(ddof=0)
    if s == 0:
        return 0.0, 3.0
    z = (r - m) / s
    return float((z**3).mean()), float((z**4).mean())


def probabilistic_sharpe(r: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """PSR (Bailey & López de Prado 2012) – P(skutečný SR > benchmark)
    s korekcí na šikmost a špičatost rozdělení výsledků obchodů."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 3 or r.std(ddof=1) == 0:
        return float("nan")
    sr = r.mean() / r.std(ddof=1)
    skew, kurt = _moments(r)
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    return _N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / denom)


def deflated_sharpe(r: np.ndarray, n_trials: int, trial_sr_std: float | None = None) -> dict:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014).

    `n_trials` = kolik variant / parametrizací jste celkem zkoušeli. Čím víc
    pokusů, tím vyšší musí být Sharpe, aby nešlo jen o nejlepší z náhod.
    `trial_sr_std` = směrodatná odchylka SR napříč pokusy; když ji neznáme,
    použije se konzervativní odhad 1/sqrt(n) (rozptyl SR čistého šumu).
    """
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 3:
        return {"dsr": float("nan"), "sr_threshold": float("nan")}
    sd = trial_sr_std if trial_sr_std is not None else 1 / math.sqrt(n)
    if n_trials <= 1:
        sr0 = 0.0
    else:
        sr0 = sd * (
            (1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
            + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e))
        )
    return {"dsr": probabilistic_sharpe(r, sr0), "sr_threshold": sr0,
            "sr": float(r.mean() / r.std(ddof=1))}


def min_trades_for_significance(expectancy_r: float, std_r: float, z: float = 1.96) -> int:
    """Kolik obchodů je potřeba, aby daná expectancy byla statisticky odlišná od 0."""
    if expectancy_r <= 0:
        return -1
    return int(math.ceil((z * std_r / expectancy_r) ** 2))


def kelly_fraction(r: np.ndarray) -> float:
    """Kelly pro výsledky v R (spojitá aproximace E[R]/E[R^2]) – podíl kapitálu
    riskovaný na obchod. V praxi používejte max. 1/4 až 1/2 Kelly."""
    r = np.asarray(r, dtype=float)
    return float(max(0.0, r.mean() / (r**2).mean())) if len(r) else 0.0


def monte_carlo_drawdown(
    r: np.ndarray, risk_per_trade: float = 0.01, n_sims: int = 5000,
    ruin_level: float = 0.5, seed: int = 0,
) -> dict:
    """Náhodné přeuspořádání obchodů (bootstrap s opakováním) → rozdělení
    max. drawdownu a pravděpodobnost ztráty `ruin_level` kapitálu."""
    r = np.asarray(r, dtype=float)
    rng = np.random.default_rng(seed)
    samples = rng.choice(r, size=(n_sims, len(r)), replace=True)
    equity = np.cumprod(1 + risk_per_trade * samples, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.ones((n_sims, 1)), equity], axis=1), axis=1)[:, 1:]
    dd = 1 - equity / peak
    max_dd = dd.max(axis=1)
    return {
        "risk_per_trade": risk_per_trade,
        "median_max_dd": float(np.median(max_dd)),
        "p95_max_dd": float(np.quantile(max_dd, 0.95)),
        "p_ruin": float((equity.min(axis=1) <= 1 - ruin_level).mean()),
        "median_final": float(np.median(equity[:, -1])),
        "p5_final": float(np.quantile(equity[:, -1], 0.05)),
    }


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    """Stabilita v čase – hrana by měla být kladná ve většině let, ne v jednom."""
    y = pd.to_datetime(trades["date"]).dt.year
    g = trades.groupby(y)["r"]
    return pd.DataFrame({"trades": g.size(), "win_rate": g.apply(lambda s: (s > 0).mean()),
                         "expectancy_r": g.mean(), "total_r": g.sum()})
