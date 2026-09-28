"""
Export the live preset table for the Sierra Chart study.

The research says a family must be traded as an ENSEMBLE of several variants, never as its single
best parameter. So for each winning family we pick representative variants: the ones whose
full-sample Sharpe is closest to the family MEDIAN (not the maximum), which is the least
cherry-picked choice, plus a spread over different regimes and exits.

Output: results/swing_presets.csv - read verbatim by the ACSIL study, so backtest and live trade
the identical rule set.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sieve import RES
from winners import family_key

WINNERS = ["LMT_RSI#<#_#ATR", "C<dvwap#sd", "C<wvwap#sd", "C06", "P_Hi#DD>#&RSI#<#", "IBS<#",
           "WR#<#", "D01", "CloseAt#dLow", "RSI#<#", "P_Hi#DD>#&IBS<#", "ConnorsRSI<#"]
ROLE = {"LMT_RSI#<#_#ATR": "R1 limit pullback", "C<dvwap#sd": "R2 vwap deviation",
        "C<wvwap#sd": "R2 vwap deviation", "C06": "R5 reclaim", "P_Hi#DD>#&RSI#<#": "R3 drawdown+osc",
        "IBS<#": "R4 close location", "WR#<#": "R4 close location", "D01": "R2 vwap deviation",
        "CloseAt#dLow": "R3 drawdown+osc", "RSI#<#": "R6 oscillator", "P_Hi#DD>#&IBS<#": "R3 drawdown+osc",
        "ConnorsRSI<#": "R6 oscillator"}
PER_FAMILY = 4


def main():
    g = pd.read_parquet(RES / "grid.parquet")
    g = g[(~g.exit.str.contains(r"\d+pt_")) & (g.side > 0) & (g.trades >= 60)].copy()
    g["fam"] = g.setup.map(family_key)
    rows = []
    for fam in WINNERS:
        q = g[g.fam == fam]
        if q.empty:
            continue
        med = q.sharpe.median()
        # representative = closest to the family median, one per (regime, exit-kind) so the
        # ensemble spreads over different regimes and exit models instead of four clones
        q = q.assign(dist=(q.sharpe - med).abs(),
                     ekind=q.exit.str.extract(r"x:([A-Za-z]+)")[0])
        pick = q.sort_values("dist").drop_duplicates(["regime"]).head(PER_FAMILY)
        if len(pick) < PER_FAMILY:
            pick = pd.concat([pick, q.sort_values("dist").head(PER_FAMILY)]).drop_duplicates(
                ["setup", "regime", "exit"]).head(PER_FAMILY)
        for i, r in enumerate(pick.itertuples(), 1):
            rows.append(dict(family=fam, role=ROLE[fam], variant=i, setup=r.setup, regime=r.regime,
                             exit=r.exit, trades=int(r.trades), win=round(r.win, 3),
                             avg_pts=round(r.avg, 2), pf=round(r.pf, 2), sharpe=round(r.sharpe, 2),
                             hold_days=round(r.hold, 1), exposure=round(r.exposure, 3)))
    df = pd.DataFrame(rows)
    df.insert(0, "id", [f"{r.family.replace('#','x')[:14]}_{r.variant}" for r in df.itertuples()])
    df.to_csv(RES / "swing_presets.csv", index=False)
    pd.set_option("display.width", 250)
    print(df.groupby(["role", "family"]).agg(variants=("variant", "size"), trades=("trades", "sum"),
                                             win=("win", "mean"), pf=("pf", "mean"),
                                             hold=("hold_days", "mean"), expo=("exposure", "sum")).round(2).to_string())
    print(f"\ntotal presets {len(df)}; combined avg exposure {df.exposure.sum():.2f} ES-equivalents")
    print(df[["id", "setup", "regime", "exit", "trades", "win", "pf", "hold_days"]].to_string(index=False))


if __name__ == "__main__":
    main()
