"""F2: which intrabar order is realistic? Simulate on 5-minute bars with both orders and compare with the
1-minute simulation (which knows the path inside the 5 minutes much better). The order that reproduces the
1-minute result on 5-minute bars is the better approximation; its error shrinks again from 1 minute to ticks."""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
from grid_run import OUT

RULES = {"fade oboji": (1, -1), "momentum oboji": (-1, 1)}


def bars5(z):
    ts = pd.DatetimeIndex(z["ts"])
    k = np.r_[0, np.cumsum((ts.floor("5min")[1:] != ts.floor("5min")[:-1]) | (z["di"][1:] != z["di"][:-1]))]
    df = pd.DataFrame({"k": k, "O": z["O"], "H": z["H"], "L": z["L"], "C": z["C"], "di": z["di"]})
    g = df.groupby("k").agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"), di=("di", "first"))
    di = g.di.to_numpy().astype(np.int32)
    last = np.r_[di[1:] != di[:-1], True]
    return {"O": g.O.to_numpy().astype(np.int32), "H": g.H.to_numpy().astype(np.int32),
            "L": g.L.to_numpy().astype(np.int32), "C": g.C.to_numpy().astype(np.int32), "di": di, "last": last}


def main():
    z = E.load()
    days = z["days"]; d0 = int(np.searchsorted(days, np.datetime64(E.START))); nd = len(days) - d0; nD = len(days)
    cfg = list(itertools.product((4, 6, 10, 20), (4, 10, 20), (0.5, 1, 2), RULES.items()))
    Xs = np.array([np.full(nD, x * 4, np.int32) for x, *_ in cfg])
    SLs = np.array([np.full(nD, s * 4, np.int32) for _, s, *_ in cfg])
    TPs = np.array([np.full(nD, round(s * r * 4), np.int32) for _, s, r, _ in cfg])
    rules = np.array([rv for *_, (_, rv) in cfg], np.int64)
    nm = np.full(len(cfg), 256, np.int64)
    out = {}
    b5 = bars5(z)
    for name, b, alt in (("1min normal", z, 0), ("1min obracene", z, 1), ("1min blizsi extrem", z, 2),
                         ("5min normal", b5, 0), ("5min obracene", b5, 1), ("5min blizsi extrem", b5, 2)):
        ok = np.ones(len(b["O"]), bool)
        DP, DN, *_ = E.run_many(b["O"], b["H"], b["L"], b["C"], b["di"], b["last"], ok, Xs, SLs, TPs, ok, ok, rules,
                                nm, True, alt, nd, d0)
        out[name] = DP.sum(1) / 4 / DN.sum(1)
        print(name, flush=True)
    R = pd.DataFrame([dict(X_body=x, SL_body=s, RRR=r, pravidlo=rn) for x, s, r, (rn, _) in cfg])
    for k, v in out.items():
        R[k] = v
    R.round(4).to_csv(os.path.join(OUT, "F_cesta_kalibrace.csv"), index=False)
    pd.set_option("display.width", 250)
    print(R.groupby(["pravidlo", "SL_body"])[list(out)].mean().round(3).to_string())


if __name__ == "__main__":
    main()
