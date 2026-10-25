"""F: sensitivity to the intrabar path: normal order (O-L-H-C for up bars) vs reversed (O-H-L-C).
Small triggers (2-4 points) depend on the unknown path inside the minute."""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
from grid_run import OUT

RULES = {"fade oboji": (1, -1), "momentum oboji": (-1, 1), "nahoda (null)": (2, 2)}


def main():
    z = E.load()
    days = z["days"]; d0 = int(np.searchsorted(days, np.datetime64(E.START))); nd = len(days) - d0
    nD = len(days); ok = np.ones(len(z["O"]), bool)
    cfg = list(itertools.product((2, 3, 4, 6, 10, 20), (4, 10, 20), (0.5, 1, 2), RULES.items()))
    Xs = np.array([np.full(nD, x * 4, np.int32) for x, *_ in cfg])
    SLs = np.array([np.full(nD, s * 4, np.int32) for _, s, *_ in cfg])
    TPs = np.array([np.full(nD, round(s * r * 4), np.int32) for _, s, r, _ in cfg])
    rules = np.array([rv for *_, (_, rv) in cfg], np.int64)
    nm = np.full(len(cfg), 256, np.int64)
    res = {}
    for alt in (False, True):
        DP, DN, *_ = E.run_many(z["O"], z["H"], z["L"], z["C"], z["di"], z["last"], ok, Xs, SLs, TPs, ok, ok, rules,
                                nm, True, alt, nd, d0)
        res[alt] = DP.sum(1) / 4 / DN.sum(1)
    R = pd.DataFrame([dict(X_body=x, SL_body=s, RRR=r, pravidlo=rn) for x, s, r, (rn, _) in cfg])
    R["hrube_b_obchod_normal"] = res[False]; R["hrube_b_obchod_obracena_cesta"] = res[True]
    R.round(4).to_csv(os.path.join(OUT, "F_cesta_v_minute.csv"), index=False)
    print(R.groupby(["pravidlo", "X_body"])[["hrube_b_obchod_normal", "hrube_b_obchod_obracena_cesta"]].mean()
          .round(3).to_string())


if __name__ == "__main__":
    main()
