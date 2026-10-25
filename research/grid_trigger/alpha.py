"""E: alpha of the best systems vs holding 1 ES contract (daily point change), selection on 2011-18, test 2019-26.
Re-runs selected systems to get daily P&L (cost 0.5 point per trade)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
from grid_run import OUT, RULES

COST = 0.5
SPLIT = np.datetime64("2019-01-01")


def daily(z, cfgs, alt=False):
    days = z["days"]; d0 = int(np.searchsorted(days, np.datetime64(E.START))); nd = len(days) - d0
    nD = len(days); ok = np.ones(len(z["O"]), bool)
    n = len(cfgs)
    Xs = np.array([np.full(nD, round(c["X_body"] * 4), np.int32) for c in cfgs])
    SLs = np.array([np.full(nD, round(c["SL_body"] * 4), np.int32) for c in cfgs])
    TPs = np.array([np.full(nD, max(1, round(c["SL_body"] * c["RRR"] * 4)), np.int32) for c in cfgs])
    rules = np.array([RULES[c["pravidlo"]] for c in cfgs], np.int64)
    nm = np.array([256 if str(c["max_obchodu"]) == "neomezeno" else int(c["max_obchodu"]) for c in cfgs], np.int64)
    DP, DN, *_ = E.run_many(z["O"], z["H"], z["L"], z["C"], z["di"], z["last"], ok, Xs, SLs, TPs, ok, ok, rules, nm,
                            True, alt, nd, d0)
    return DP / 4.0 - COST * DN, days[d0:]


def bh_points(z, days):
    """1 ES contract held: daily change of the last close of each Globex day (points)"""
    c = pd.Series(z["C"] / 4.0).groupby(z["di"]).last()
    d0 = int(np.searchsorted(z["days"], days[0]))
    return c.diff().to_numpy()[d0:]


def reg(y, x):
    X = np.c_[np.ones(len(x)), x]
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ b
    se = np.sqrt(res.var(ddof=2) / len(y))
    return b[0] * 252, b[0] / se, b[1]


def main():
    z = E.load()
    B = pd.read_csv(os.path.join(OUT, "B_grid_body.csv"))
    B = B[B.max_obchodu.astype(str) == "1"]
    # selection on 2011-18 only: best 10 per rule by net points/trade 2011-18 with >= 50 trades a year
    sel = (B[B.obchodu_rocne >= 50].sort_values("b_obchod_2011_18_0.5", ascending=False)
           .groupby("pravidlo").head(5))
    cfgs = sel.to_dict("records")
    net, days = daily(z, cfgs)
    bh = bh_points(z, days)
    disc = days < SPLIT
    rows = []
    for c, y in zip(cfgs, net):
        r = {k: c[k] for k in ("pravidlo", "X_body", "SL_body", "RRR", "obchodu_rocne")}
        r["b_obchod_2011_18"] = c["b_obchod_2011_18_0.5"]
        r["body_rocne_2019_26"] = y[~disc].sum() / (~disc).sum() * 252
        a, t, beta = reg(y[~disc], bh[~disc])
        r.update(alfa_body_rok_2019_26=a, alfa_t=t, beta=beta,
                 BH_body_rok_2019_26=bh[~disc].sum() / (~disc).sum() * 252)
        rows.append(r)
    R = pd.DataFrame(rows)
    R.round(3).to_csv(os.path.join(OUT, "E_alfa_vyber.csv"), index=False)
    pd.set_option("display.width", 250)
    print(R.round(3).to_string())


if __name__ == "__main__":
    main()
