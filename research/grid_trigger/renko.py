"""Renko continuation: after a move of X points, probability that the next X move goes the same way.
Random walk = 0.5 (plus a tiny drift effect). < 0.5 = mean reversion (chop), > 0.5 = momentum.
Path resolution check: the same on 1-minute and on 5-minute bars (coarser bars hide reversals inside the bar),
the gap between them shows the direction of the bias of the 1-minute estimate."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


@njit(cache=True)
def renko(O, H, L, C, grp, ngrp, x):
    same = np.zeros(ngrp); tot = np.zeros(ngrp)
    anchor = O[0]; prev = O[0]; last = 0
    pts = np.zeros(4, np.int64)
    for i in range(len(O)):
        if C[i] >= O[i]:
            pts[0] = O[i]; pts[1] = L[i]; pts[2] = H[i]; pts[3] = C[i]
        else:
            pts[0] = O[i]; pts[1] = H[i]; pts[2] = L[i]; pts[3] = C[i]
        cur = prev
        for leg in range(4):
            tgt = pts[leg]
            while cur != tgt:
                if leg == 0:
                    cur = tgt
                elif tgt > cur:
                    cur += 1
                else:
                    cur -= 1
                ev = 0
                if cur <= anchor - x:
                    ev = -1; anchor = cur
                elif cur >= anchor + x:
                    ev = 1; anchor = cur
                if ev != 0:
                    if last != 0:
                        tot[grp[i]] += 1
                        if ev == last:
                            same[grp[i]] += 1
                    last = ev
        prev = cur
    return same, tot


def agg(z, minutes):
    if minutes == 1:
        return z["O"], z["H"], z["L"], z["C"], z["ts"]
    ts = pd.DatetimeIndex(z["ts"])
    key = ts.floor(f"{minutes}min")
    df = pd.DataFrame({"O": z["O"], "H": z["H"], "L": z["L"], "C": z["C"]}, index=ts)
    g = df.groupby(key).agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"))
    return g.O.to_numpy(), g.H.to_numpy(), g.L.to_numpy(), g.C.to_numpy(), g.index.to_numpy()


def main():
    z = E.load()
    rows = []
    for m in (1, 5):
        O, H, L, C, ts = agg(z, m)
        ts = pd.DatetimeIndex(ts)
        keep = ts >= E.START
        O, H, L, C, ts = O[keep], H[keep], L[keep], C[keep], ts[keep]
        yr = ts.year.to_numpy() - 2011
        hr = ts.hour + ts.minute / 60
        rth = ((hr >= 9.5) & (hr < 16)).astype(np.int64)
        for x_pts in (1, 2, 3, 4, 6, 8, 10, 15, 20, 30, 50):
            x = int(x_pts * 4)
            s, t = renko(O, H, L, C, yr.astype(np.int64), 16, x)
            s2, t2 = renko(O, H, L, C, rth, 2, x)
            r = dict(bary_min=m, X_body=x_pts, n=int(t.sum()), p_pokracovani=s.sum() / t.sum(),
                     p_ETH=s2[0] / t2[0], p_RTH=s2[1] / t2[1])
            for y in range(16):
                r[str(2011 + y)] = s[y] / t[y] if t[y] > 0 else np.nan
            rows.append(r)
            print(m, x_pts, round(r["p_pokracovani"], 4), int(t.sum()), flush=True)
    R = pd.DataFrame(rows)
    R.round(4).to_csv(os.path.join(OUT, "A_renko.csv"), index=False)
    print(R.round(3).to_string())


if __name__ == "__main__":
    main()
