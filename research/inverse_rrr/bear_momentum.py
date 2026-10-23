"""Bear-regime intraday momentum, a simple automatic system (rules fixed from the DISC family scan).

Rules:
  regime  previous close below MA200 (bear); control: above MA200 (bull)
  window  10:00-15:00 ET; the first minute when (price - globex open 18:00) >= +x * ATR -> long,
          <= -x * ATR -> short (one trade per day, entry at the next minute's open)
  exit    TP / SL in ATR or the RTH close 16:00 (variants below), cost 0.5 point
  x       0.6 and 1.0 ATR (both were in the scan)
Output: out/bear_momentum_*.csv, per year and period, vs buy & hold.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
from irr_engine import load_1m  # noqa: E402

OUT = os.path.join(HERE, "out")
COST = 0.5


@njit(cache=True)
def scan(o, h, l, c, gmin, day_start, day_end, atr, ok, x, tp, sl, w0, w1):
    nd = len(day_start)
    res = np.full((nd, 4), np.nan)        # side, pnl points, code, entry gmin
    for d in range(nd):
        if not ok[d]:
            continue
        s0 = day_start[d]; s1 = day_end[d]
        op = o[s0]; a = atr[d]
        side = 0; ent = -1
        for k in range(s0, s1 - 1):
            g = gmin[k]
            if g < w0:
                continue
            if g > w1:
                break
            mv = (c[k] - op) / a
            if mv >= x:
                side = 1; ent = k + 1; break
            if mv <= -x:
                side = -1; ent = k + 1; break
        if side == 0:
            continue
        ep = o[ent]; pnl = np.nan; code = 0
        for k in range(ent, s1):
            if gmin[k] >= 1320:
                pnl = side * (o[k] - ep); break
            fav = (h[k] - ep) if side > 0 else (ep - l[k])
            adv = (ep - l[k]) if side > 0 else (h[k] - ep)
            if sl > 0 and adv >= sl * a:
                pnl = -sl * a; code = -1; break
            if tp > 0 and fav >= tp * a:
                pnl = tp * a; code = 1; break
            pnl = side * (c[k] - ep)
        res[d, 0] = side; res[d, 1] = pnl - COST; res[d, 2] = code; res[d, 3] = gmin[ent]
    return res


def main():
    import features as F
    T = F.load()["T"]
    X = load_1m()
    gday = X.gday.astype("datetime64[D]")
    days, start = np.unique(gday, return_index=True)
    end = np.r_[start[1:], len(gday)]
    idx = pd.to_datetime(days)
    atr = T.ATR.shift().reindex(idx).to_numpy()
    bear = (T.C < T.ma200).shift().reindex(idx).fillna(False).to_numpy().astype(bool)
    good = np.isfinite(atr) & (idx.year >= 2009)
    rows, yearly = [], {}
    variants = [("do close", 0, 0), ("TP 0,4 / SL 0,8", 0.4, 0.8), ("TP 0,3 / SL 1,5 (obrácené)", 0.3, 1.5),
                ("TP 0,5 / SL 0,5", 0.5, 0.5), ("jen SL 0,5", 0, 0.5)]
    for reg_name, mask in (("medvědí (pod MA200)", bear), ("býčí (nad MA200)", ~bear)):
        for x in (0.6, 1.0):
            for vname, tp, sl in variants:
                r = scan(X.o, X.h, X.l, X.c, X.gmin.astype(np.int64), start, end, np.nan_to_num(atr, nan=1.0),
                         good & mask, x, tp, sl, 960, 1260)
                D = pd.DataFrame(r, columns=["side", "pts", "code", "gm"], index=idx).dropna()
                D["R"] = D.pts / pd.Series(atr, index=idx).reindex(D.index)
                D["y"] = D.index.year
                per = np.where(D.y <= 2017, "2009–17", np.where(D.y <= 2021, "2018–21", "2022–26"))
                row = dict(rezim=reg_name, x=x, exit=vname, obchodu=len(D), R=D.R.mean(),
                           t=D.R.mean() / D.R.std() * np.sqrt(len(D)) if len(D) > 2 else np.nan,
                           long_R=D.R[D.side > 0].mean(), short_R=D.R[D.side < 0].mean(), win=(D.pts > 0).mean(),
                           body_celkem=D.pts.sum())
                for p in ("2009–17", "2018–21", "2022–26"):
                    v = D.R[per == p]; row[f"R {p}"] = v.mean(); row[f"n {p}"] = len(v)
                rows.append(row)
                if reg_name.startswith("medv") and x == 0.6:
                    yearly[vname] = D.groupby("y").pts.sum()
    S = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(S.round(3).to_string())
    S.round(4).to_csv(os.path.join(OUT, "bear_momentum_summary.csv"), index=False)
    Y = pd.DataFrame(yearly)
    bh = T.C.groupby(T.C.index.year).last().diff()
    Y["B&H body"] = bh.reindex(Y.index)
    Y["dní v medvědím režimu"] = pd.Series(bear & good, index=idx).groupby(idx.year).sum().reindex(Y.index)
    print(Y.round(1).to_string())
    Y.round(2).to_csv(os.path.join(OUT, "bear_momentum_years.csv"))


if __name__ == "__main__":
    main()
