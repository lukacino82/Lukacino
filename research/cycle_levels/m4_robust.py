"""Robustness of the only hint (chart grid m = 4: bounce before penetration at 0.5 spacing): other symmetric distances,
declustered events (one per 10 calendar days), split 2018-21 / 2022-26, vs the same 200 random-phase grids."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import grid_data as G
from levels_test import NNULL, OUT, run_grid


def stats(H, L, C, ts, u):
    bar, lvl, dr, back, thru, endc, unit = run_grid(H, L, C, 4, u)
    t = ts[bar]
    keep = np.ones(len(bar), bool); last = None
    for i in range(len(bar)):
        if last is not None and (t[i] - last) < np.timedelta64(10, "D"):
            keep[i] = False
        else:
            last = t[i]
    row = {}
    for i, dd in enumerate((0.25, 0.5, 1.0)):
        tb = np.where(back[:, i] >= 0, back[:, i], 1e12)
        tt = np.where(thru[:, i] >= 0, thru[:, i], 1e12)
        b = tb < tt
        row[f"bounce {dd}"] = b.mean()
        row[f"bounce {dd} declust"] = b[keep].mean()
        for p, msk in (("2018–21", t < np.datetime64("2022-01-01")), ("2022–26", t >= np.datetime64("2022-01-01"))):
            row[f"bounce {dd} {p}"] = b[msk].mean()
    row["n"] = len(bar); row["n declust"] = keep.sum()
    return row


def main():
    d = G.load(); ts = d["ts"]
    us = np.random.default_rng(11).random(NNULL)
    real = stats(d["H"], d["L"], d["C"], ts, 0.0)
    N = pd.DataFrame([stats(d["H"], d["L"], d["C"], ts, u) for u in us])
    R = pd.DataFrame([dict(metrika=k, real=v, null_mean=N[k].mean(), p=(N[k] >= v).mean()) for k, v in real.items()])
    print(R.round(3).to_string()); R.round(4).to_csv(os.path.join(OUT, "m4_robust.csv"), index=False)


if __name__ == "__main__":
    main()
