"""Příkazová řádka.

Příklady:
  python -m session_edge profile  --csv es_5m.csv --data-tz UTC --tz America/New_York
  python -m session_edge validate --csv es_5m.csv --strategy us_orb30 --rrr 2 --max-trades 1 --exit-time 15:55
  python -m session_edge walkforward --csv es_5m.csv --strategy us_orb30 --exit-time 15:55
  python -m session_edge validate --synthetic --strategy us_orb30   # demo bez dat
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from .config import BacktestConfig, RiskConfig
from .data import load_csv, synthetic_intraday
from .profile import volatility_profile, weekday_profile
from .strategies import PRESETS, STRATEGY_CLASSES, make_strategy
from .validation import param_grid, validate, walk_forward


def _parse_value(v: str):
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def _load(args) -> pd.DataFrame:
    if args.synthetic:
        return synthetic_intraday(days=args.days, orb_drift=args.inject_edge, seed=args.seed)
    if not args.csv:
        sys.exit("Zadejte --csv soubor nebo --synthetic")
    return load_csv(args.csv, tz=args.data_tz)


def _risk(args) -> RiskConfig:
    return RiskConfig(
        stop_mode=args.stop_mode, stop_value=args.stop, target_mode=args.target_mode,
        target_value=args.target, rrr=args.rrr, max_trades_per_day=args.max_trades,
        exit_time=args.exit_time, breakeven_at_r=args.breakeven, cost_per_trade=args.cost,
    )


def _fmt(d: dict) -> str:
    def conv(x):
        if isinstance(x, (np.floating, float)):
            return round(float(x), 4)
        if isinstance(x, (np.integer,)):
            return int(x)
        return x
    return json.dumps({k: conv(v) for k, v in d.items()}, ensure_ascii=False, indent=2, default=str)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="session_edge", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["profile", "backtest", "validate", "walkforward", "list"])
    ap.add_argument("--csv")
    ap.add_argument("--data-tz", default="UTC", help="časová zóna časů v CSV")
    ap.add_argument("--synthetic", action="store_true", help="syntetická data (demo)")
    ap.add_argument("--days", type=int, default=1000)
    ap.add_argument("--inject-edge", type=float, default=0.0, help="umělá hrana v syntetice")
    ap.add_argument("--seed", type=int, default=0)

    ap.add_argument("--strategy", default="us_orb30")
    ap.add_argument("--set", action="append", default=[], metavar="KLÍČ=HODNOTA",
                    help="parametr strategie, např. --set range_end=09:45")
    ap.add_argument("--tz", default="America/New_York", help="zóna pro profil volatility")
    ap.add_argument("--bucket", default="30min")

    g = ap.add_argument_group("risk management")
    g.add_argument("--stop-mode", default="strategy", choices=["strategy", "atr", "points", "range"])
    g.add_argument("--stop", type=float, default=1.0, help="hodnota stopu dle --stop-mode")
    g.add_argument("--target-mode", default="rrr", choices=["rrr", "atr", "points", "none"])
    g.add_argument("--target", type=float, default=0.0)
    g.add_argument("--rrr", type=float, default=2.0)
    g.add_argument("--max-trades", type=int, default=1, help="max. obchodů za den")
    g.add_argument("--exit-time", default=None, help="nucené uzavření, např. 15:55")
    g.add_argument("--breakeven", type=float, default=None, help="posun SL na BE po X R")
    g.add_argument("--cost", type=float, default=0.0, help="náklady round-trip v bodech ceny")

    v = ap.add_argument_group("validace")
    v.add_argument("--trials", type=int, default=1, help="kolik variant jste celkem zkoušeli (pro DSR)")
    v.add_argument("--random-runs", type=int, default=200)
    v.add_argument("--risk-pct", type=float, default=1.0, help="%% kapitálu riskovaných na obchod")
    v.add_argument("--train-days", type=int, default=500)
    v.add_argument("--test-days", type=int, default=125)
    v.add_argument("--out", help="uložit obchody do CSV")
    args = ap.parse_args(argv)

    if args.command == "list":
        print("Předvolby:", ", ".join(sorted(PRESETS)))
        print("Třídy:", ", ".join(sorted(STRATEGY_CLASSES)))
        return

    data = _load(args)
    if args.command == "profile":
        pd.set_option("display.width", 120)
        print(volatility_profile(data, args.tz, args.bucket).round(3).to_string())
        print()
        print(weekday_profile(data, args.tz).round(3).to_string())
        return

    overrides = dict(kv.split("=", 1) for kv in args.set)
    strategy = make_strategy(args.strategy, **{k: _parse_value(v) for k, v in overrides.items()})
    cfg = BacktestConfig(risk=_risk(args))

    if args.command in ("backtest", "validate"):
        rep = validate(data, strategy, cfg, n_trials=args.trials,
                       n_random=args.random_runs if args.command == "validate" else 0,
                       risk_per_trade=args.risk_pct / 100, seed=args.seed) \
            if args.command == "validate" else None
        if rep is None:
            from .engine import run_backtest
            from .stats import summary
            trades = run_backtest(data, strategy, cfg)
            print(_fmt(summary(trades)))
        else:
            trades = rep["trades"]
            print(f"Strategie: {rep['strategy']}  {rep['params']}")
            print(f"Risk: {rep['risk']}\n")
            print("== Souhrn ==\n" + _fmt(rep["summary"]))
            if "bootstrap" in rep:
                print("\n== Bootstrap expectancy (R) ==\n" + _fmt(rep["bootstrap"]))
                print("\n== Test náhodného směru ==\n" + _fmt(rep["random_direction"]))
                print("\n== Deflated Sharpe ==\n" + _fmt(rep["deflated_sharpe"]))
                print(f"\nPotřebný počet obchodů pro významnost: {rep['min_trades_needed']}")
                print(f"Kelly (plný): {rep['kelly']:.3f} → doporučeno max. {rep['kelly'] / 4:.3%} riziko/obchod")
                print("\n== Monte Carlo (risk %.2f%%) ==\n" % args.risk_pct + _fmt(rep["monte_carlo"]))
                print("\n== Po letech ==\n" + rep["by_year"].round(3).to_string())
                print("\n== Kontroly ==")
                for k, ok in rep["checks"].items():
                    print(f"  [{'OK' if ok else '--'}] {k}")
            print(f"\nVERDIKT: {rep['verdict']}")
        if args.out:
            trades.to_csv(args.out, index=False)
        return

    if args.command == "walkforward":
        grid = param_grid(**{"risk.rrr": [1.0, 1.5, 2.0, 3.0],
                             "risk.stop_mode": ["strategy", "range"],
                             "risk.stop_value": [0.5, 1.0]})
        res = walk_forward(data, strategy, cfg, grid, args.train_days, args.test_days)
        print(res["windows"].to_string())
        print("\n== OOS (spojené neviděné úseky) ==\n" + _fmt(res["oos_summary"]))
        if args.out:
            res["oos_trades"].to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
