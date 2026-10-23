"""Do the cycle levels (grid_data.py) work as trading levels on ES 2018-07 .. 2026-09 (1-min, cash-equivalent)?

Grid depth m: level spacing = cycle / m (m = 4 is the chart: red, 1/4, 1/2, 3/4; m = 8 .. 64 finer, intraday).
Event: first touch of a level after price has been >= 0.5 spacing away from it. Direction = side of approach.
From the touch (entry exactly at the level) the first-passage outcome is recorded for distances in spacing units
D = 0.25, 0.5, 1, 2 back (bounce) and through (penetration), max 60 trading days.
  fade:     TP = a back, SL = b through   (level-defined RRR a/b)
  breakout: TP = b through, SL = a back  (mirror image)
Cost 0.5 point per round turn. Unresolved trades are closed at the horizon.
Null: 200 grids with the same construction and a random phase (all levels shifted by a random fraction of a cycle in
log space). p = share of null grids with a result >= the real grid. Excess = real minus null mean (removes what any
grid of the same density gives: drift, volatility clustering, round-trip structure).
Also by level type for m = 4 (red / half / quarter), and the cycle-completion test (3/4 reached, falls back to 1/2 ->
does it later complete to the next red level? and the mirror 1/4 -> red below).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid_data as G

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
D = np.array([0.25, 0.5, 1.0, 2.0])
MS = (4, 8, 16, 32, 64)
NNULL = 200
COST = 0.5
HOR = 60 * 1380


@njit(cache=True)
def scan(gh, gl, gc, D, hor):
    """gh/gl/gc: grid coordinate * m (levels at integers). Returns events (bar, level, dir) and first-passage bars
    back[e, i] / thru[e, i] for D[i] (-1 = not hit within horizon) and coordinate at the horizon end."""
    n = len(gh)
    lo = int(np.floor(gl.min())) - 2
    hi = int(np.ceil(gh.max())) + 2
    armed = np.zeros(hi - lo + 1, np.bool_)
    maxe = 200000
    ev_bar = np.empty(maxe, np.int64); ev_lvl = np.empty(maxe, np.int64); ev_dir = np.empty(maxe, np.int64)
    ne = 0
    for t in range(1, n):
        a = int(np.ceil(gl[t])); b = int(np.floor(gh[t]))
        for j in range(a, b + 1):
            if armed[j - lo]:
                armed[j - lo] = False
                d = 1 if gc[t - 1] < j else -1          # +1: approach from below (fade = short), -1 from above
                if gc[t - 1] == j:
                    continue
                if ne < maxe:
                    ev_bar[ne] = t; ev_lvl[ne] = j; ev_dir[ne] = d; ne += 1
        # re-arm levels the price has moved >= 0.5 away from
        j0 = int(np.floor(gl[t] - 0.5)); j1 = int(np.ceil(gh[t] + 0.5))
        for j in range(max(lo, j0 - 3), min(hi, j1 + 3) + 1):
            if not armed[j - lo] and (gl[t] >= j + 0.5 or gh[t] <= j - 0.5):
                armed[j - lo] = True
    nd = len(D)
    back = -np.ones((ne, nd), np.int64); thru = -np.ones((ne, nd), np.int64); endc = np.zeros(ne)
    for e in range(ne):
        t0 = ev_bar[e]; j = ev_lvl[e]; d = ev_dir[e]
        # entry bar: the part beyond the level (in the approach direction) happened after the touch
        ext = (gh[t0] - j) if d == 1 else (j - gl[t0])
        for i in range(nd):
            if ext >= D[i]:
                thru[e, i] = 0
        last = min(n - 1, t0 + hor)
        for t in range(t0 + 1, last + 1):
            if d == 1:
                up = gh[t] - j; dn = j - gl[t]
                th, bk = up, dn
            else:
                th, bk = j - gl[t], gh[t] - j
            for i in range(nd):
                if thru[e, i] < 0 and th >= D[i]:
                    thru[e, i] = t - t0
                if back[e, i] < 0 and bk >= D[i]:
                    back[e, i] = t - t0
            if back[e, nd - 1] >= 0 or thru[e, nd - 1] >= 0:
                break
        endc[e] = (gc[last] - j) * (-d)                   # in units, positive = back (fade profit)
    return ev_bar[:ne], ev_lvl[:ne], ev_dir[:ne], back, thru, endc


def outcomes(back, thru, endc, unit_pts):
    """fade results in R for every (a back, b through) pair; breakout = mirror"""
    res = {}
    for ia, a in enumerate(D):
        for ib, b in enumerate(D):
            tb = np.where(back[:, ia] >= 0, back[:, ia], 10**12)
            tt = np.where(thru[:, ib] >= 0, thru[:, ib], 10**12)
            win = tb < tt                                   # ties (same bar) -> loss (tt <= tb)
            loss = tt <= tb
            open_ = (tb == 10**12) & (tt == 10**12)
            r_fade = np.where(win & ~open_, a / b, np.where(loss & ~open_, -1.0, endc / b))
            c = COST / (b * unit_pts)
            res[(a, b)] = (r_fade - c, -r_fade * (b / a) - COST / (a * unit_pts))   # breakout: R in units of a
    return res


def run_grid(H, L, C, m, u):
    r0 = G.R0 * G.RATIO ** u
    gh = G.coord(H, r0) * m; gl = G.coord(L, r0) * m; gc = G.coord(C, r0) * m
    bar, lvl, dr, back, thru, endc = scan(gh, gl, gc, D, HOR)
    lv_price = G.level_price(lvl / m, r0)
    unit = G.level_price((lvl + 1) / m, r0) - lv_price
    return bar, lvl, dr, back, thru, endc, unit


def summarize(H, L, C, m, u):
    bar, lvl, dr, back, thru, endc, unit = run_grid(H, L, C, m, u)
    res = outcomes(back, thru, endc, unit)
    row = dict(n=len(bar), bounce_05=np.mean(np.where(back[:, 1] >= 0, back[:, 1], 1e12) < np.where(thru[:, 1] >= 0, thru[:, 1], 1e12)))
    for (a, b), (rf, rb) in res.items():
        row[f"fade {a}/{b}"] = rf.mean()
        row[f"break {b}/{a}"] = rb.mean()
    typ = np.mod(lvl, m) if m == 4 else None
    return row, (bar, lvl, dr, back, thru, endc, unit, typ, res)


def main():
    os.makedirs(OUT, exist_ok=True)
    d = G.load()
    H, L, C = d["H"], d["L"], d["C"]
    ts = pd.DatetimeIndex(d["ts"])
    rng = np.random.default_rng(11)
    us = rng.random(NNULL)
    rows = []; detail = {}
    for m in MS:
        real, det = summarize(H, L, C, m, 0.0)
        detail[m] = det
        nulls = pd.DataFrame([summarize(H, L, C, m, u)[0] for u in us])
        for k, v in real.items():
            rows.append(dict(m=m, metrika=k, real=v, null_mean=nulls[k].mean(), null_sd=nulls[k].std(),
                             excess=v - nulls[k].mean(), z=(v - nulls[k].mean()) / nulls[k].std() if nulls[k].std() > 0 else np.nan,
                             p=(nulls[k] >= v).mean()))
        print("m", m, "done", real["n"], "events")
    S = pd.DataFrame(rows)
    S.round(4).to_csv(os.path.join(OUT, "levels_vs_null.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    show = S[S.metrika.isin(["n", "bounce_05", "fade 0.25/0.25", "fade 0.5/0.5", "fade 1.0/1.0", "fade 1.0/0.25", "fade 1.0/0.5",
                             "fade 2.0/0.5", "break 1.0/0.25", "break 1.0/0.5", "break 2.0/0.5", "break 1.0/1.0"])]
    print(show.round(3).to_string())
    # extremes across all configs: how many p < 0.05 / > 0.95
    cfg = S[S.metrika.str.startswith(("fade", "break"))]
    print("konfigurací", len(cfg), "p<0.05:", (cfg.p < 0.05).sum(), " p>0.95:", (cfg.p > 0.95).sum())
    # m = 4 by level type (0 red, 2 half, 1/3 quarter): real only, R of fade 1.0/0.5 and bounce
    bar, lvl, dr, back, thru, endc, unit, typ, res = detail[4]
    tb = np.where(back[:, 1] >= 0, back[:, 1], 1e12); tt = np.where(thru[:, 1] >= 0, thru[:, 1], 1e12)
    T4 = pd.DataFrame(dict(datum=ts[bar].date, level=np.round(G.level_price(lvl / 4), 2), typ=np.select([typ == 0, typ == 2], ["červená (cyklus)", "1/2"], "1/4 nebo 3/4"),
                           smer=np.where(dr == 1, "zdola", "shora"), bounce_pred_pruraz=(tb < tt),
                           fade_R_1_05=res[(1.0, 0.5)][0], fade_R_05_05=res[(0.5, 0.5)][0]))
    T4.to_csv(os.path.join(OUT, "m4_events.csv"), index=False)
    print(T4.groupby("typ")[["bounce_pred_pruraz", "fade_R_1_05", "fade_R_05_05"]].agg(["mean", "count"]).round(3))
    print(T4.to_string())
    # null for level types with m = 4
    trow = []
    for u in np.r_[0.0, us]:
        _, (b_, l_, d_, bk, th, ec, un, ty, rs) = summarize(H, L, C, 4, u)
        tb = np.where(bk[:, 1] >= 0, bk[:, 1], 1e12); tt = np.where(th[:, 1] >= 0, th[:, 1], 1e12)
        for name, msk in (("red", ty == 0), ("half", ty == 2), ("quarter", (ty == 1) | (ty == 3))):
            trow.append(dict(u=u, typ=name, n=msk.sum(), bounce=(tb < tt)[msk].mean(), fadeR=rs[(0.5, 0.5)][0][msk].mean()))
    TT = pd.DataFrame(trow)
    out = []
    for name, g in TT.groupby("typ"):
        rv = g[g.u == 0].iloc[0]; nv = g[g.u != 0]
        out.append(dict(typ=name, n=rv.n, bounce=rv.bounce, bounce_null=nv.bounce.mean(), p_bounce=(nv.bounce >= rv.bounce).mean(),
                        fadeR=rv.fadeR, fadeR_null=nv.fadeR.mean(), p_fade=(nv.fadeR >= rv.fadeR).mean()))
    TY = pd.DataFrame(out); print(TY.round(3)); TY.round(4).to_csv(os.path.join(OUT, "m4_level_types.csv"), index=False)
    # cycle completion on daily bars
    Dd = pd.DataFrame(dict(H=H, L=L), index=ts).resample("1D").agg({"H": "max", "L": "min"}).dropna()
    crow = []
    for scale in (1, 4, 16):                                  # 1 = red cycle; 4 / 16 = sub-cycles (1/4, 1/16 of a cycle)
        for u in np.r_[0.0, us]:
            hd = Dd.H.to_numpy(); ld = Dd.L.to_numpy()
            r0 = G.R0 * G.RATIO ** u
            gh = G.coord(hd, r0) * scale; gl = G.coord(ld, r0) * scale
            hits = completion_coord(gh, gl)
            if hits:
                hh = np.array(hits, float)
                for side in (1, -1):
                    s = hh[hh[:, 0] == side]
                    crow.append(dict(scale=scale, u=u, side=side, n=len(s), p_done=s[:, 2].mean() if len(s) else np.nan,
                                     dni=np.nanmedian(s[:, 3]) if len(s) and s[:, 2].any() else np.nan))
    CR = pd.DataFrame(crow)
    cout = []
    for (sc, sd), g in CR.groupby(["scale", "side"]):
        rv = g[g.u == 0]
        if not len(rv):
            continue
        rv = rv.iloc[0]; nv = g[g.u != 0]
        cout.append(dict(cyklus={1: "celý cyklus (červená→červená)", 4: "1/4 cyklu", 16: "1/16 cyklu"}[sc],
                         smer="nahoru (3/4 → zpět 1/2 → dokončí?)" if sd == 1 else "dolů (1/4 → zpět 1/2 → dokončí?)",
                         n=int(rv.n), p_dokonceni=rv.p_done, null_p=nv.p_done.mean(), null_p05=nv.p_done.quantile(0.05),
                         null_p95=nv.p_done.quantile(0.95), p_hodnota=(nv.p_done >= rv.p_done).mean(), median_dni=rv.dni))
    CO = pd.DataFrame(cout); print(CO.round(3).to_string()); CO.round(4).to_csv(os.path.join(OUT, "completion.csv"), index=False)


def completion_coord(gh, gl, hor=250):
    n = len(gh); hits = []
    for side in (1, -1):
        t = 0
        while t < n:
            k = np.floor(gl[t]) if side == 1 else np.floor(gh[t] - 1e-12)
            if side == 1:
                ok = gh[t] >= k + 0.75 and gh[t] < k + 1 and gl[t] < k + 0.75
            else:
                ok = gl[t] <= k + 0.25 and gl[t] > k and gh[t] > k + 0.25
            if not ok:
                t += 1; continue
            tgt = k + 1 if side == 1 else k
            s = t + 1; fell = -1
            while s < n:
                if (side == 1 and gh[s] >= tgt) or (side == -1 and gl[s] <= tgt):
                    break
                if (side == 1 and gl[s] <= k + 0.5) or (side == -1 and gh[s] >= k + 0.5):
                    fell = s; break
                s += 1
            if fell < 0:
                t = s + 1; continue
            e = fell + 1; done = False
            while e < min(n, fell + hor + 1):
                if (side == 1 and gh[e] >= tgt) or (side == -1 and gl[e] <= tgt):
                    done = True; break
                e += 1
            hits.append((side, fell, done, (e - fell) if done else np.nan))
            t = e + 1
    return hits


if __name__ == "__main__":
    main()
