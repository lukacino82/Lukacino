"""Pre-registered check from cycle_levels/ (2018-26 chart grid hint: bounce of 1/8 cycle at red and half W1 lines):
fade TP = SL = 1/8 cycle at W1 lines, real vs 200 random-phase grids, separately for 2008-18 (out of sample) and 2018-26."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import bcl_data as BD
from bcl_test import GRIDS, NNULL, OUT, run

PER = np.datetime64("2018-07-08")


def stats(H, L, C, ts, c, r0, hor):
    bar, typ, dr, res = run(H, L, C, c, r0, hor)
    r = res[("fade", 0.125, 0.125)]
    out = {}
    for tname, tv in (("červená", (0,)), ("1/2", (2,)), ("červená + 1/2", (0, 2))):
        for pn, pm in (("2008–18", ts[bar] < PER), ("2018–26", ts[bar] >= PER), ("celé", np.ones(len(bar), bool))):
            m = np.isin(typ, tv) & pm
            out[(tname, pn)] = (r[m].mean() if m.any() else np.nan, int(m.sum()), (r[m] > 0).mean() if m.any() else np.nan)
    return out


def main():
    df = BD.load()
    b5 = df.set_index("ts").resample("5min").agg({"O": "first", "H": "max", "L": "min", "C": "last"}).dropna()
    H, L, C, ts = b5.H.to_numpy(), b5.L.to_numpy(), b5.C.to_numpy(), b5.index.values
    c, r0, hd = GRIDS["W1"]
    real = stats(H, L, C, ts, c, r0, hd * 276)
    us = np.random.default_rng(23).random(NNULL)
    nulls = [stats(H, L, C, ts, c, r0 * (1 / (1 - c)) ** u, hd * 276) for u in us]
    rows = []
    for k, (v, n, w) in real.items():
        nv = np.array([x[k][0] for x in nulls])
        rows.append(dict(typ=k[0], obdobi=k[1], n=n, win=w, R=v, null_R=np.nanmean(nv), p=np.nanmean(nv >= v)))
    T = pd.DataFrame(rows); print(T.round(3).to_string()); T.round(4).to_csv(os.path.join(OUT, "w1_preregistered.csv"), index=False)


if __name__ == "__main__":
    main()
