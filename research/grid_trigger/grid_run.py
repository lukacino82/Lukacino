"""B: full grid in points (intraday, flat at 16:59 ET): trigger X x SL x RRR x rule x max open trades.
C: the same in ATR units (daily, hourly, weekly ATR). Output: one row per system with gross and net results."""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
SPLIT = np.datetime64("2019-01-01")
RULES = {"fade long (pokles->long)": (1, 0), "fade short (rust->short)": (0, -1),
         "momentum long (rust->long)": (0, 1), "momentum short (pokles->short)": (-1, 0),
         "fade oboji": (1, -1), "momentum oboji": (-1, 1), "long vzdy (prikupovani+prumerovani)": (1, 1),
         "nahoda (null)": (2, 2)}
NMAX = (1, 3, 10, 256)
RRR = (0.25, 0.5, 0.75, 1, 1.2, 1.5, 2, 3, 5, 10)
COSTS = (0.25, 0.5)


def stats(DP, DN, CNT, MO, MS, meta, days, SLpts):
    """DP/DN per config per day (gross ticks); SLpts: mean SL in points per config (for R)"""
    rows = []
    disc = days < SPLIT
    yrs = len(days) / 252
    year = pd.DatetimeIndex(days).year.to_numpy()
    for c in range(DP.shape[0]):
        n = DN[c].sum()
        g = DP[c].astype(np.float64) / 4
        r = dict(meta[c]); r.update(obchodu=int(n), obchodu_rocne=n / yrs)
        if n == 0:
            rows.append(r); continue
        r.update(win=CNT[c, 0] / n, sl_podil=CNT[c, 1] / n, cas_podil=CNT[c, 2] / n,
                 hrube_b_obchod=g.sum() / n, max_otevreno=int(MO[c]), max_serie_SL=int(MS[c]))
        for cost in COSTS:
            net = g - cost * DN[c]
            tag = f"_{cost:g}"
            sd = net.std()
            r["cisty_b_obchod" + tag] = net.sum() / n
            r["R_obchod" + tag] = net.sum() / n / SLpts[c]
            r["body_rocne" + tag] = net.sum() / yrs
            r["t" + tag] = net.mean() / sd * np.sqrt(len(net)) if sd > 0 else np.nan
            eq = np.cumsum(net)
            r["maxDD_body" + tag] = (eq - np.maximum.accumulate(eq)).min()
            n1 = DN[c][disc].sum(); n2 = DN[c][~disc].sum()
            r["b_obchod_2011_18" + tag] = net[disc].sum() / n1 if n1 else np.nan
            r["b_obchod_2019_26" + tag] = net[~disc].sum() / n2 if n2 else np.nan
            if cost == 0.5:
                yp = pd.Series(net).groupby(year).sum()
                r["kladnych_let_0.5"] = int((yp > 0).sum())
        rows.append(r)
    return rows


def run_points(z, alt=False, flatten=True, tag="B_grid_body"):
    days = z["days"]; d0 = int(np.searchsorted(days, np.datetime64(E.START))); nd = len(days) - d0
    nD = len(days); ok = np.ones(len(z["O"]), bool)
    rows = []
    for X in (2, 3, 4, 6, 8, 10, 15, 20, 30):
        cfg = list(itertools.product((2, 4, 6, 8, 10, 15, 20, 30, 50), RRR, RULES.items(), NMAX))
        cfg = [c for c in cfg if round(c[0] * c[1] * 4) >= 1]
        n = len(cfg)
        Xs = np.full((n, nD), X * 4, np.int32)
        SLs = np.array([np.full(nD, s * 4, np.int32) for s, *_ in cfg])
        TPs = np.array([np.full(nD, max(1, round(s * r * 4)), np.int32) for s, r, *_ in cfg])
        rules = np.array([rv for _, _, (_, rv), _ in cfg], np.int64)
        nm = np.array([m for *_, m in cfg], np.int64)
        t = time.time()
        DP, DN, CNT, MO, MS = E.run_many(z["O"], z["H"], z["L"], z["C"], z["di"], z["last"], ok, Xs, SLs, TPs,
                                         ok, ok, rules, nm, flatten, alt, nd, d0)
        meta = [dict(X_body=X, SL_body=s, RRR=r, TP_body=round(s * r * 4) / 4, pravidlo=rn,
                     max_obchodu="neomezeno" if m == 256 else m) for s, r, (rn, _), m in cfg]
        rows += stats(DP, DN, CNT, MO, MS, meta, days[d0:], np.array([s for s, *_ in cfg], float))
        print(tag, "X", X, n, "cfg", round(time.time() - t), "s", flush=True)
    R = pd.DataFrame(rows)
    R.round(4).to_csv(os.path.join(OUT, f"{tag}.csv"), index=False)
    return R


def run_atr(z, which, tag):
    """X, SL in fractions of ATR (atr_d / atr_h / atr_w, points); TP = SL x RRR"""
    days = z["days"]; d0 = int(np.searchsorted(days, np.datetime64(E.START))); nd = len(days) - d0
    nD = len(days); ok = np.ones(len(z["O"]), bool)
    atr = pd.Series(z[which]).ffill().bfill().to_numpy()
    kx_set = {"atr_d": (0.02, 0.04, 0.06, 0.1, 0.15, 0.25), "atr_h": (0.1, 0.25, 0.5, 1.0, 1.5, 2.5),
              "atr_w": (0.01, 0.02, 0.03, 0.05, 0.08, 0.12)}[which]
    ks_set = {"atr_d": (0.03, 0.05, 0.1, 0.15, 0.25, 0.4), "atr_h": (0.25, 0.5, 1.0, 1.5, 2.5, 4.0),
              "atr_w": (0.01, 0.02, 0.04, 0.06, 0.1, 0.15)}[which]
    rows = []
    for kx in kx_set:
        cfg = list(itertools.product(ks_set, RRR, RULES.items(), NMAX))
        n = len(cfg)
        xt = np.maximum(1, np.round(atr * kx * 4)).astype(np.int32)
        Xs = np.tile(xt, (n, 1))
        SLs = np.array([np.maximum(1, np.round(atr * s * 4)).astype(np.int32) for s, *_ in cfg])
        TPs = np.array([np.maximum(1, np.round(atr * s * r * 4)).astype(np.int32) for s, r, *_ in cfg])
        rules = np.array([rv for _, _, (_, rv), _ in cfg], np.int64)
        nm = np.array([m for *_, m in cfg], np.int64)
        t = time.time()
        DP, DN, CNT, MO, MS = E.run_many(z["O"], z["H"], z["L"], z["C"], z["di"], z["last"], ok, Xs, SLs, TPs,
                                         ok, ok, rules, nm, True, False, nd, d0)
        slp = np.array([np.nanmean(atr[d0:] * s) for s, *_ in cfg])
        meta = [dict(ATR=which, X_atr=kx, SL_atr=s, RRR=r, pravidlo=rn,
                     max_obchodu="neomezeno" if m == 256 else m) for s, r, (rn, _), m in cfg]
        rows += stats(DP, DN, CNT, MO, MS, meta, days[d0:], slp)
        print(tag, "kx", kx, n, "cfg", round(time.time() - t), "s", flush=True)
    R = pd.DataFrame(rows)
    R.round(4).to_csv(os.path.join(OUT, f"{tag}.csv"), index=False)
    return R


if __name__ == "__main__":
    z = E.load()
    what = sys.argv[1] if len(sys.argv) > 1 else "points"
    if what == "points":
        run_points(z)
    elif what == "alt":
        run_points(z, alt=True, tag="B_grid_body_alt")
    elif what == "hold":
        run_points(z, flatten=False, tag="B_grid_body_hold")
    else:
        run_atr(z, what, f"C_grid_{what}")
