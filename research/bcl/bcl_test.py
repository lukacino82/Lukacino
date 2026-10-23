"""BCL (big cycle lines) on US500Cash-equivalent prices 2008-2026: every TP/SL variant vs random-phase grids.

Lines (fitted to the user's charts to +-0.03 point, logic from the course Excel 'ciara-MC'): the cycle is the move that
takes a fully margined account to the 30 % stop-out, c = 0.7 x price / leverage; red lines are geometric,
R_k = R_0 / (1 - c)^k, and each red-to-red cycle is split linearly into quarters (blue 3/4, yellow 1/2, purple 1/4).
  W1 grid: c = 0.280281 (leverage 2.5), R_0 = 2908.44
  D1 grid: c = 0.028028 (leverage 25),  R_0 = 7219.03
Event: first touch of a line after price has been >= 1/8 cycle away. Entry exactly at the line (limit / stop order).
First passage of a = 1/8 .. 2 cycles back (bounce) and b through (penetration), 5-min bars, horizon 250 (W1) / 60 (D1)
trading days, open trades closed at the horizon.  fade: TP a back, SL b through;  breakout: TP b through, SL a back.
Cost 0.6 point per round turn. R = result / SL distance.
Null: 200 grids of the same construction with a random phase. p = share of null grids >= real. Family-wise check:
the best configuration of the real grid vs the distribution of the best configuration of each null grid.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcl_data as BD

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
GRIDS = {"W1": (0.280281, 2908.44, 250), "D1": (0.028028, 7219.03, 60)}
DC = np.array([0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0])          # distances in cycles
COST = 0.6
NNULL = 200
TYPES = {"červená": (0,), "1/2": (2,), "1/4 a 3/4": (1, 3), "všechny": (0, 1, 2, 3)}


def coord(p, c, r0):
    lq = -np.log(1 - c)
    k = np.floor(np.log(p / r0) / lq)
    lo = r0 * np.exp(k * lq)
    return k + (p - lo) / (lo * (np.exp(lq) - 1))


def level_price(g, c, r0):
    lq = -np.log(1 - c)
    k = np.floor(g)
    lo = r0 * np.exp(k * lq)
    return lo + (g - k) * lo * (np.exp(lq) - 1)


@njit(cache=True)
def scan(gh, gl, gc, D, rearm, hor):
    n = len(gh)
    lo = int(np.floor(gl.min())) - 2
    hi = int(np.ceil(gh.max())) + 2
    armed = np.zeros(hi - lo + 1, np.bool_)
    maxe = 400000
    ev_bar = np.empty(maxe, np.int64); ev_lvl = np.empty(maxe, np.int64); ev_dir = np.empty(maxe, np.int64)
    ne = 0
    for t in range(1, n):
        a = int(np.ceil(gl[t])); b = int(np.floor(gh[t]))
        for j in range(a, b + 1):
            if armed[j - lo]:
                armed[j - lo] = False
                if gc[t - 1] == j:
                    continue
                d = 1 if gc[t - 1] < j else -1
                if ne < maxe:
                    ev_bar[ne] = t; ev_lvl[ne] = j; ev_dir[ne] = d; ne += 1
        j0 = int(np.floor(gl[t] - rearm)); j1 = int(np.ceil(gh[t] + rearm))
        for j in range(max(lo, j0 - 3), min(hi, j1 + 3) + 1):
            if not armed[j - lo] and (gl[t] >= j + rearm or gh[t] <= j - rearm):
                armed[j - lo] = True
    nd = len(D)
    back = -np.ones((ne, nd), np.int64); thru = -np.ones((ne, nd), np.int64); endc = np.zeros(ne)
    for e in range(ne):
        t0 = ev_bar[e]; j = ev_lvl[e]; d = ev_dir[e]
        ext = (gh[t0] - j) if d == 1 else (j - gl[t0])
        for i in range(nd):
            if ext >= D[i]:
                thru[e, i] = 0
        last = min(n - 1, t0 + hor)
        for t in range(t0 + 1, last + 1):
            if d == 1:
                th = gh[t] - j; bk = j - gl[t]
            else:
                th = j - gl[t]; bk = gh[t] - j
            for i in range(nd):
                if thru[e, i] < 0 and th >= D[i]:
                    thru[e, i] = t - t0
                if back[e, i] < 0 and bk >= D[i]:
                    back[e, i] = t - t0
            if back[e, nd - 1] >= 0 or thru[e, nd - 1] >= 0:
                break
        endc[e] = (gc[last] - j) * (-d)
    return ev_bar[:ne], ev_lvl[:ne], ev_dir[:ne], back, thru, endc


def run(H, L, C, c, r0, hor_bars):
    m = 4
    gh = coord(H, c, r0) * m; gl = coord(L, c, r0) * m; gc = coord(C, c, r0) * m
    D = DC * m
    bar, lvl, dr, back, thru, endc = scan(gh, gl, gc, D, 0.5, hor_bars)
    cyc_pts = level_price((lvl + m) / m, c, r0) - level_price(lvl / m, c, r0)        # 1 cycle in points at the line
    typ = np.mod(lvl, m)
    big = 10**12
    res = {}
    for ia, a in enumerate(DC):
        tb = np.where(back[:, ia] >= 0, back[:, ia], big)
        for ib, b in enumerate(DC):
            tt = np.where(thru[:, ib] >= 0, thru[:, ib], big)
            open_ = (tb == big) & (tt == big)
            win = (tb < tt) & ~open_
            pnl = np.where(win, a, np.where(open_, endc / m, -b))                   # fade, in cycles
            res[("fade", a, b)] = pnl / b - COST / (b * cyc_pts)
            res[("breakout", b, a)] = -pnl / a - COST / (a * cyc_pts)               # TP b, SL a
    return bar, typ, dr, res


def summary(bar, typ, res, ts, split=None):
    rows = {}
    for tname, tv in TYPES.items():
        msk = np.isin(typ, tv)
        for key, r in res.items():
            x = r[msk]
            rows[(tname,) + key] = (x.mean() if len(x) else np.nan, len(x))
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    df = BD.load()
    b5 = df.set_index("ts").resample("5min").agg({"O": "first", "H": "max", "L": "min", "C": "last"}).dropna()
    H, L, C = b5.H.to_numpy(), b5.L.to_numpy(), b5.C.to_numpy()
    ts = b5.index.values
    per = np.where(ts < np.datetime64("2018-07-08"), "2008–18 (rekonstrukce)", "2018–26 (broker)")
    us = np.random.default_rng(23).random(NNULL)
    allrows = []; best = []
    for g, (c, r0, hd) in GRIDS.items():
        hor = hd * 276
        bar, typ, dr, res = run(H, L, C, c, r0, hor)
        real = summary(bar, typ, res, ts)
        # per-period real
        realp = {}
        for p in np.unique(per):
            mk = per[bar] == p
            realp[p] = summary(bar[mk], typ[mk], {k: v[mk] for k, v in res.items()}, ts)
        nulls = []
        for u in us:
            r0u = r0 * (1 / (1 - c)) ** u
            bb, tt_, dd, rr = run(H, L, C, c, r0u, hor)
            nulls.append(summary(bb, tt_, rr, ts))
        keys = list(real.keys())
        NM = np.array([[n[k][0] for k in keys] for n in nulls])
        for i, k in enumerate(keys):
            v, n = real[k]
            row = dict(mrizka=g, typ=k[0], smer=k[1], TP_cyklu=k[2], SL_cyklu=k[3], n=n, R=v,
                       null_R=np.nanmean(NM[:, i]), null_sd=np.nanstd(NM[:, i]), p=np.mean(NM[:, i] >= v))
            for p in realp:
                row[f"R {p}"] = realp[p][k][0]; row[f"n {p}"] = realp[p][k][1]
            allrows.append(row)
        # family-wise: best excess (R - null mean) over configs with n >= 30
        nn = np.array([real[k][1] for k in keys])
        ok = nn >= 30
        mu = np.nanmean(NM, axis=0)
        real_ex = np.array([real[k][0] for k in keys]) - mu
        real_best = np.nanmax(np.where(ok, real_ex, -np.inf))
        null_best = np.nanmax(np.where(ok, NM - mu, -np.inf), axis=1)
        best.append(dict(mrizka=g, nejlepsi_excess_R=real_best, null_best_mean=null_best.mean(),
                         null_best_p95=np.quantile(null_best, 0.95), p_family=np.mean(null_best >= real_best),
                         konfiguraci=int(ok.sum())))
        print(g, "events", len(bar), "done", flush=True)
    S = pd.DataFrame(allrows)
    S.round(4).to_csv(os.path.join(OUT, "bcl_all_configs.csv"), index=False)
    BST = pd.DataFrame(best); BST.round(4).to_csv(os.path.join(OUT, "bcl_familywise.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(BST.round(3).to_string())
    for g in GRIDS:
        x = S[(S.mrizka == g) & (S.n >= 30)].copy(); x["ex"] = x.R - x.null_R
        print(f"== {g}: počet konfigurací", len(x), " p<0.05:", (x.p < 0.05).sum(), " p>0.95:", (x.p > 0.95).sum())
        print(x.sort_values("ex", ascending=False).head(15).round(3).to_string())
        print(x[(x.smer == "fade") & (x.TP_cyklu == x.SL_cyklu)].round(3).to_string())


if __name__ == "__main__":
    main()
