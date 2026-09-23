"""Bar-by-bar simulace obchodů bez look-ahead biasu.

Zásady:
* ATR a včerejší close se počítají výhradně z předchozích dní.
* Stop entry (průraz) se plní na úrovni průrazu, nebo na open baru při gapu.
* Na vstupním baru stop-entry obchodu se kontroluje jen SL (nevíme, zda TP
  přišel až po vstupu) – konzervativní předpoklad.
* Když jeden bar zasáhne SL i TP, počítá se SL (conservative_intrabar).
* Gap přes SL/TP se plní na open baru (realisticky horší/lepší cena).
* Nucený výstup: na open prvního baru s časem >= exit_time, jinak na close
  posledního baru dne.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .config import BacktestConfig, RiskConfig
from .strategies import DayContext, Signal, Strategy

TRADE_COLUMNS = [
    "date", "entry_time", "exit_time", "direction", "entry", "stop", "target",
    "exit", "exit_reason", "risk", "pnl", "r", "mfe_r", "mae_r", "tag",
]


def daily_context(df: pd.DataFrame, atr_days: int) -> pd.DataFrame:
    """Denní OHLC + ATR a včerejší hodnoty posunuté o den (žádný look-ahead)."""
    dates = df.index.date
    daily = df.groupby(dates).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    prev_close = daily["close"].shift(1)
    tr = np.maximum(daily["high"], prev_close) - np.minimum(daily["low"], prev_close)
    tr = tr.fillna(daily["high"] - daily["low"])
    daily["atr"] = tr.rolling(atr_days, min_periods=atr_days).mean().shift(1)
    daily["prev_close"] = prev_close
    daily["prev_range"] = (daily["high"] - daily["low"]).shift(1)
    return daily


def _risk_distance(sig: Signal, rc: RiskConfig, atr: float) -> float:
    if rc.stop_mode == "strategy":
        return abs(sig.entry - sig.stop)
    if rc.stop_mode == "atr":
        return rc.stop_value * atr
    if rc.stop_mode == "points":
        return rc.stop_value
    if rc.stop_mode == "range":
        return rc.stop_value * sig.ref_range
    raise ValueError(rc.stop_mode)


def _target_distance(risk: float, rc: RiskConfig, atr: float) -> Optional[float]:
    if rc.target_mode == "rrr":
        return rc.rrr * risk
    if rc.target_mode == "atr":
        return rc.target_value * atr
    if rc.target_mode == "points":
        return rc.target_value
    return None


@dataclass
class PreparedDay:
    ctx: DayContext
    signals: list[Signal]
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    times: pd.DatetimeIndex
    tod: np.ndarray  # časy dne (datetime.time) pro nucený výstup


def _simulate(
    day: PreparedDay, sig: Signal, direction: int, ctx: DayContext, cfg: BacktestConfig
) -> Optional[dict]:
    rc = cfg.risk
    o, h, l, c = day.o, day.h, day.l, day.c
    times = day.times
    n = len(o)

    risk = _risk_distance(sig, rc, ctx.atr)
    if not np.isfinite(risk) or risk < rc.min_risk:
        return None
    entry = sig.entry
    stop = entry - direction * risk
    tdist = _target_distance(risk, rc, ctx.atr)
    target = entry + direction * tdist if tdist is not None else None

    start = sig.bar_pos
    exit_pos = n  # první bar, na jehož open se nuceně zavírá
    if rc.exit_time is not None:
        later = np.flatnonzero(day.tod >= rc.exit_time)
        later = later[later > start]
        exit_pos = later[0] if len(later) else n
        if day.tod[start] >= rc.exit_time:
            return None

    exit_price = exit_reason = None
    exit_idx = None
    best = worst = 0.0  # MFE / MAE v cenových jednotkách
    be_armed = rc.breakeven_at_r is not None
    for j in range(start, exit_pos):
        first = j == start
        if first and sig.fill == "close":
            continue  # vstup na close – kontrola až od dalšího baru
        hi, lo = h[j], l[j]
        fav = (hi - entry) if direction > 0 else (entry - lo)
        adv = (entry - lo) if direction > 0 else (hi - entry)

        # gap přes stop/target na open (neplatí pro vstupní bar)
        if not first:
            oj = o[j]
            if (direction > 0 and oj <= stop) or (direction < 0 and oj >= stop):
                exit_price, exit_reason, exit_idx = oj, "stop", j
                break
            if target is not None and (
                (direction > 0 and oj >= target) or (direction < 0 and oj <= target)
            ):
                exit_price, exit_reason, exit_idx = oj, "target", j
                break

        hit_stop = lo <= stop if direction > 0 else hi >= stop
        check_target = not (first and sig.fill == "intrabar")
        hit_target = (
            check_target and target is not None
            and (hi >= target if direction > 0 else lo <= target)
        )
        if hit_stop and hit_target:
            if cfg.conservative_intrabar:
                exit_price, exit_reason = stop, "stop"
            else:
                exit_price, exit_reason = target, "target"
            exit_idx = j
            break
        if hit_stop:
            exit_price, exit_reason, exit_idx = stop, "stop", j
            best = max(best, fav)
            worst = max(worst, risk)
            break
        if hit_target:
            exit_price, exit_reason, exit_idx = target, "target", j
            best = max(best, tdist)
            break
        best = max(best, fav)
        worst = max(worst, adv)
        if be_armed and best >= rc.breakeven_at_r * risk:
            stop = entry  # platí od dalšího baru
            be_armed = False

    if exit_price is None:
        if exit_pos < n:
            exit_price, exit_reason, exit_idx = o[exit_pos], "time", exit_pos
        else:
            exit_price, exit_reason, exit_idx = c[n - 1], "eod", n - 1

    if exit_reason == "stop" and stop == entry:
        exit_reason = "breakeven"
    pnl = direction * (exit_price - entry) - rc.cost_per_trade
    return {
        "date": ctx.date,
        "entry_time": times[start],
        "exit_time": times[exit_idx],
        "exit_pos": exit_idx,
        "direction": direction,
        "entry": entry,
        "stop": entry - direction * risk,
        "target": target,
        "exit": exit_price,
        "exit_reason": exit_reason,
        "risk": risk,
        "pnl": pnl,
        "r": pnl / risk,
        "mfe_r": best / risk,
        "mae_r": worst / risk,
        "tag": sig.tag,
    }


def prepare(data: pd.DataFrame, strategy: Strategy, cfg: BacktestConfig) -> list[PreparedDay]:
    """Rozdělí data na dny, spočítá kontext a signály (jednou – signály
    nezávisí na risk nastavení, takže se dají opakovaně simulovat)."""
    df = data.tz_convert(strategy.tz)
    daily = daily_context(df, cfg.atr_days)
    out = []
    for date, day in df.groupby(df.index.date, sort=True):
        row = daily.loc[date]
        if not np.isfinite(row["atr"]) or row["atr"] <= 0:
            continue
        ctx = DayContext(
            date=date,
            atr=float(row["atr"]),
            prev_close=None if pd.isna(row["prev_close"]) else float(row["prev_close"]),
            prev_range=None if pd.isna(row["prev_range"]) else float(row["prev_range"]),
        )
        signals = strategy.generate(day, ctx)
        if not signals:
            continue
        out.append(PreparedDay(ctx, signals, day["open"].values, day["high"].values,
                               day["low"].values, day["close"].values, day.index,
                               np.array(day.index.time)))
    return out


def simulate(
    prepared: list[PreparedDay],
    cfg: BacktestConfig,
    direction_fn: Optional[Callable[[Signal, np.random.Generator], int]] = None,
    seed: int = 0,
) -> pd.DataFrame:
    rc = cfg.risk
    rng = np.random.default_rng(seed)
    trades = []
    for day in prepared:
        busy_until = -1
        taken = 0
        for sig in day.signals:
            if taken >= rc.max_trades_per_day:
                break
            if sig.bar_pos <= busy_until:
                continue  # pozice ještě otevřená (max. 1 pozice současně)
            d = direction_fn(sig, rng) if direction_fn else sig.direction
            t = _simulate(day, sig, d, day.ctx, cfg)
            if t is None:
                continue
            busy_until = t.pop("exit_pos")
            trades.append(t)
            taken += 1
    return pd.DataFrame(trades, columns=TRADE_COLUMNS)


def run_backtest(
    data: pd.DataFrame,
    strategy: Strategy,
    cfg: Optional[BacktestConfig] = None,
    direction_fn: Optional[Callable[[Signal, np.random.Generator], int]] = None,
    seed: int = 0,
) -> pd.DataFrame:
    """Spustí backtest. `direction_fn` umožní přepsat směr obchodu (použito
    v testu náhodného směru – nulová hypotéza „směr je hod mincí“)."""
    cfg = cfg or BacktestConfig()
    return simulate(prepare(data, strategy, cfg), cfg, direction_fn, seed)


def random_direction(sig: Signal, rng: np.random.Generator) -> int:
    return int(rng.choice((-1, 1)))
