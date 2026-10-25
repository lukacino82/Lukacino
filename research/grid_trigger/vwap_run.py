"""D: grid systems filtered by weekly / monthly VWAP (Globex week from Sunday 18:00 ET, Globex month).
Filter 've smeru' = longs only above the VWAP, shorts only below; 'proti' = the opposite.
VWAP is computed from typical price x volume up to the previous bar (no look-ahead)."""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
from grid_run import OUT, RRR, stats

RULES = {"fade long (pokles->long)": (1, 0), "momentum long (rust->long)": (0, 1),
         "fade short (rust->short)": (0, -1), "momentum short (pokles->short)": (-1, 0)}


def vwaps(z):
    days = pd.DatetimeIndex(z["days"])
    gday = days[z["di"]]
    tp = (z["H"] + z["L"] + z["C"]) / 12.0
    v = z["vol"]
    out = {}
    wk = (gday - pd.to_timedelta(gday.weekday, unit="D")).to_numpy()      # Monday of the Globex week
    mo = gday.to_period("M").to_timestamp().to_numpy()
    for name, key in (("W", wk), ("M", mo)):
        df = pd.DataFrame({"k": key, "pv": tp * v, "v": v})
        cpv = df.groupby("k").pv.cumsum().to_numpy(); cv = df.groupby("k").v.cumsum().to_numpy()
        vw = np.where(cv > 0, cpv / np.maximum(cv, 1), np.nan)
        vw = pd.Series(vw).shift(1).to_numpy()                              # known before the bar
        first = np.r_[True, key[1:] != key[:-1]]
        vw[first] = np.nan
        out[name] = pd.Series(vw).ffill().to_numpy()
    prevc = np.r_[z["C"][0], z["C"][:-1]] / 4.0
    return {k: prevc > v for k, v in out.items()}          # True = price above the VWAP


def main():
    z = E.load()
    days = z["days"]; d0 = int(np.searchsorted(days, np.datetime64(E.START))); nd = len(days) - d0
    nD = len(days); ok = np.ones(len(z["O"]), bool)
    above = vwaps(z)
    print({k: round(v[z['di'] >= d0].mean(), 3) for k, v in above.items()}, flush=True)
    filters = {"bez filtru": (ok, ok)}
    for k in ("W", "M"):
        a = above[k]
        filters[f"ve smeru {k}-VWAP"] = (a, ~a)
        filters[f"proti {k}-VWAP"] = (~a, a)
    a = above["W"] & above["M"]; b = ~above["W"] & ~above["M"]
    filters["ve smeru W+M"] = (a, b)
    rows = []
    for fname, (aL, aS) in filters.items():
        cfg = list(itertools.product((4, 6, 10, 15, 20), (4, 6, 10, 15, 20, 30), RRR, RULES.items(), (1, 256)))
        n = len(cfg)
        Xs = np.array([np.full(nD, x * 4, np.int32) for x, *_ in cfg])
        SLs = np.array([np.full(nD, s * 4, np.int32) for _, s, *_ in cfg])
        TPs = np.array([np.full(nD, max(1, round(s * r * 4)), np.int32) for _, s, r, *_ in cfg])
        rules = np.array([rv for *_, (_, rv), _ in cfg], np.int64)
        nm = np.array([m for *_, m in cfg], np.int64)
        t = time.time()
        DP, DN, CNT, MO, MS = E.run_many(z["O"], z["H"], z["L"], z["C"], z["di"], z["last"], ok, Xs, SLs, TPs,
                                         aL, aS, rules, nm, True, False, nd, d0)
        meta = [dict(filtr=fname, X_body=x, SL_body=s, RRR=r, pravidlo=rn,
                     max_obchodu="neomezeno" if m == 256 else m) for x, s, r, (rn, _), m in cfg]
        rows += stats(DP, DN, CNT, MO, MS, meta, days[d0:], np.array([s for _, s, *_ in cfg], float))
        print("D", fname, n, "cfg", round(time.time() - t), "s", flush=True)
    R = pd.DataFrame(rows)
    R.round(4).to_csv(os.path.join(OUT, "D_vwap_filtr.csv"), index=False)


if __name__ == "__main__":
    main()
