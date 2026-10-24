"""BCL follow-up after the user's master document (24.10.2026):
 (1) cycle = 4 K / 9990 of the red line (K = 7 / 70 / 700) - identical to our fit;
 (2) the line set is re-anchored after a completed cycle + reversal (H5), so a single fixed grid over 2008-2026 is not
     what the indicator showed historically;
 (3) trend context matters (trend-correction / with-trend vs counter-trend scenarios, H6).

Part A - trend split on the fixed grids (W1 K=700, D1 K=70): every event is tagged with-trend / counter-trend
         (daily close vs 200-day average at the previous day) for fade and breakout.
Part B - pivot-anchored grids (H5): causal zigzag on 5-min closes; a pivot is a high/low after a leg of >= 1 cycle that
         is confirmed by a reversal of theta cycles. From the confirmation bar the active grid has its red line at the
         pivot price (R = pivot), until the next confirmed pivot. Only touches after confirmation count.
         Null: the same pivot times, anchor shifted by a random fraction of a cycle.
Outcomes in price: first passage of a .. b cycles back / through from the touched line, 5-min bars, cost 0.6 point.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcl_data as BD
from bcl_test import DC, OUT, coord, level_price

COST = 0.6
K_C = {7: 4 * 7 / 9990, 70: 4 * 70 / 9990, 700: 4 * 700 / 9990}


@njit(cache=True)
def zigzag(c, cyc, theta, minleg):
    """causal pivots: (confirm_bar, pivot_price). A pivot needs a prior leg >= minleg cycles and a reversal of
    theta cycles; cyc = cycle as a fraction of price."""
    n = len(c)
    conf = np.empty(n, np.int64); piv = np.empty(n); k = 0
    d = 0; ext = c[0]; start = c[0]
    for t in range(1, n):
        if d == 0:
            if c[t] > start * (1 + theta * cyc):
                d = 1; ext = c[t]
            elif c[t] < start * (1 - theta * cyc):
                d = -1; ext = c[t]
        elif d == 1:
            if c[t] > ext:
                ext = c[t]
            elif c[t] <= ext * (1 - theta * cyc):
                if ext - start >= minleg * cyc * ext:
                    conf[k] = t; piv[k] = ext; k += 1
                d = -1; start = ext; ext = c[t]
        else:
            if c[t] < ext:
                ext = c[t]
            elif c[t] >= ext * (1 + theta * cyc):
                if start - ext >= minleg * cyc * start:
                    conf[k] = t; piv[k] = ext; k += 1
                d = 1; start = ext; ext = c[t]
    return conf[:k], piv[:k]


@njit(cache=True)
def scan_seg(gh, gl, gc, seg, rearm, bigN):
    """first touches of integer levels of a piecewise grid (seg id per bar, -1 = none); a new segment starts disarmed"""
    n = len(gh)
    off = bigN // 2
    armed = np.zeros(bigN, np.bool_)
    ev_bar = np.empty(2000000, np.int64); ev_lvl = np.empty(2000000, np.int64); ev_dir = np.empty(2000000, np.int64)
    ne = 0
    for t in range(1, n):
        if seg[t] < 0:
            continue
        if seg[t] != seg[t - 1]:
            armed[:] = False
            continue
        a = int(np.ceil(gl[t])); b = int(np.floor(gh[t]))
        for j in range(a, b + 1):
            if armed[j + off]:
                armed[j + off] = False
                if gc[t - 1] == j:
                    continue
                if ne < 2000000:
                    ev_bar[ne] = t; ev_lvl[ne] = j; ev_dir[ne] = 1 if gc[t - 1] < j else -1; ne += 1
        j0 = int(np.floor(gl[t] - rearm)); j1 = int(np.ceil(gh[t] + rearm))
        for j in range(j0 - 3, j1 + 4):
            if not armed[j + off] and (gl[t] >= j + rearm or gh[t] <= j - rearm):
                armed[j + off] = True
    return ev_bar[:ne], ev_lvl[:ne], ev_dir[:ne]


@njit(cache=True)
def outcomes_price(H, L, C, ev_bar, ev_dir, lp, cp, D, hor):
    ne = len(ev_bar); nd = len(D)
    back = -np.ones((ne, nd), np.int64); thru = -np.ones((ne, nd), np.int64); endc = np.zeros(ne)
    n = len(H)
    for e in range(ne):
        t0 = ev_bar[e]; d = ev_dir[e]; p = lp[e]; u = cp[e]
        ext = ((H[t0] - p) if d == 1 else (p - L[t0])) / u
        for i in range(nd):
            if ext >= D[i]:
                thru[e, i] = 0
        last = min(n - 1, t0 + hor)
        for t in range(t0 + 1, last + 1):
            if d == 1:
                th = (H[t] - p) / u; bk = (p - L[t]) / u
            else:
                th = (p - L[t]) / u; bk = (H[t] - p) / u
            for i in range(nd):
                if thru[e, i] < 0 and th >= D[i]:
                    thru[e, i] = t - t0
                if back[e, i] < 0 and bk >= D[i]:
                    back[e, i] = t - t0
            if back[e, nd - 1] >= 0 or thru[e, nd - 1] >= 0:
                break
        endc[e] = (C[last] - p) * (-d) / u
    return back, thru, endc


def results(back, thru, endc, cp):
    big = 10**12; res = {}
    for ia, a in enumerate(DC):
        tb = np.where(back[:, ia] >= 0, back[:, ia], big)
        for ib, b in enumerate(DC):
            tt = np.where(thru[:, ib] >= 0, thru[:, ib], big)
            open_ = (tb == big) & (tt == big)
            win = (tb < tt) & ~open_
            pnl = np.where(win, a, np.where(open_, endc, -b))
            res[("fade", a, b)] = pnl / b - COST / (b * cp)
            res[("breakout", b, a)] = -pnl / a - COST / (a * cp)
    return res


def run_grid(H, L, C, c, r0_bar, seg, hor):
    """r0_bar: red anchor per bar; seg: segment id per bar (-1 = no active grid)."""
    m = 4
    r0 = np.where(seg >= 0, r0_bar, C)
    gh = coord(H, c, r0) * m; gl = coord(L, c, r0) * m; gc = coord(C, c, r0) * m
    bar, lvl, dr = scan_seg(gh, gl, gc, seg, 0.5, 4000)
    lp = level_price(lvl / m, c, r0[bar])
    cp = level_price((lvl + m) / m, c, r0[bar]) - lp
    back, thru, endc = outcomes_price(H, L, C, bar, dr, lp, cp, DC, hor)
    return bar, np.mod(lvl, m), dr, results(back, thru, endc, cp)


def tag_summary(bar, typ, dr, res, trend):
    """fade with trend = long fade from above in an uptrend or short fade from below in a downtrend;
    breakout with trend = the opposite pairing (breaking upward in an uptrend / downward in a downtrend)."""
    up = trend[bar]
    fade_with = ((dr == -1) & up) | ((dr == 1) & ~up)
    out = {}
    for tname, tv in (("červená", (0,)), ("1/2", (2,)), ("všechny", (0, 1, 2, 3))):
        mt = np.isin(typ, tv)
        for key, r in res.items():
            w = fade_with if key[0] == "fade" else ~fade_with
            for ctx, msk in (("s trendem", mt & w), ("proti trendu", mt & ~w), ("vše", mt)):
                x = r[msk]
                out[(tname, ctx) + key] = (x.mean() if len(x) else np.nan, int(len(x)))
    return out


def compare(name, real, nulls, rows, extra):
    keys = list(real.keys())
    NM = np.array([[nn[k][0] for k in keys] for nn in nulls])
    mu = np.nanmean(NM, axis=0)
    for i, k in enumerate(keys):
        v, n = real[k]
        rows.append(dict(test=name, **extra, typ=k[0], kontext=k[1], smer=k[2], TP_cyklu=k[3], SL_cyklu=k[4], n=n,
                         R=v, null_R=mu[i], excess=v - mu[i], p=np.nanmean(NM[:, i] >= v) if np.isfinite(v) else np.nan))
    nn_ = np.array([real[k][1] for k in keys]); ok = nn_ >= 30
    rex = np.array([real[k][0] for k in keys]) - mu
    rb = np.nanmax(np.where(ok, rex, -np.inf)); nb = np.nanmax(np.where(ok, NM - mu, -np.inf), axis=1)
    return dict(test=name, **extra, konfiguraci=int(ok.sum()), nejlepsi_excess=rb, null_best_mean=np.nanmean(nb),
                null_best_p95=np.nanquantile(nb, 0.95), p_family=np.nanmean(nb >= rb))


def main():
    os.makedirs(OUT, exist_ok=True)
    df = BD.load()
    b5 = df.set_index("ts").resample("5min").agg({"O": "first", "H": "max", "L": "min", "C": "last"}).dropna()
    H, L, C, ts = b5.H.to_numpy(), b5.L.to_numpy(), b5.C.to_numpy(), b5.index
    dc = b5.C.resample("1D").last().dropna()
    up_d = (dc > dc.rolling(200).mean()).shift(1).fillna(True)
    trend = up_d.reindex(ts.normalize()).ffill().fillna(True).to_numpy().astype(bool)
    rng = np.random.default_rng(31)
    rows, fam = [], []
    # Part A: fixed grids with trend split
    for g, (K, r0, hd, nnull) in {"W1 pevná (K=700)": (700, 2908.44, 250, 200),
                                  "D1 pevná (K=70)": (70, 7219.03, 60, 200)}.items():
        c = K_C[K]; q = 1 / (1 - c); seg = np.zeros(len(C), np.int64)
        real = tag_summary(*run_grid(H, L, C, c, np.full(len(C), r0), seg, hd * 276), trend)
        nulls = [tag_summary(*run_grid(H, L, C, c, np.full(len(C), r0 * q ** u), seg, hd * 276), trend)
                 for u in rng.random(nnull)]
        fam.append(compare(g, real, nulls, rows, dict(K=K, theta=np.nan, pivotu=np.nan)))
        print(g, "done", flush=True)
    # Part B: pivot-anchored grids
    for K, theta, hd, nnull in ((70, 0.5, 60, 100), (70, 1.0, 60, 100), (700, 0.25, 250, 100), (700, 0.5, 250, 100)):
        c = K_C[K]; q = 1 / (1 - c)
        conf, piv = zigzag(C, c, theta, 1.0)
        seg = np.full(len(C), -1, np.int64); r0b = np.full(len(C), np.nan)
        for i in range(len(conf)):
            e = conf[i + 1] if i + 1 < len(conf) else len(C)
            seg[conf[i] + 1:e] = i; r0b[conf[i] + 1:e] = piv[i]
        real = tag_summary(*run_grid(H, L, C, c, r0b, seg, hd * 276), trend)
        nulls = [tag_summary(*run_grid(H, L, C, c, r0b * q ** u, seg, hd * 276), trend) for u in rng.random(nnull)]
        name = f"kotva na pivotu K={K}, potvrzení {theta} cyklu"
        fam.append(compare(name, real, nulls, rows, dict(K=K, theta=theta, pivotu=len(conf))))
        print(name, "pivots", len(conf), flush=True)
    S = pd.DataFrame(rows); S.round(4).to_csv(os.path.join(OUT, "bcl_anchor_trend.csv"), index=False)
    F = pd.DataFrame(fam); F.round(4).to_csv(os.path.join(OUT, "bcl_anchor_familywise.csv"), index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300)
    print(F.round(3).to_string())
    x = S[S.n >= 30]
    print(x.sort_values("excess", ascending=False).groupby("test").head(5).round(3).to_string())
    print(x[(x.smer == "fade") & (x.TP_cyklu == x.SL_cyklu) & (x.typ == "všechny") & (x.TP_cyklu.isin([0.125, 0.25, 0.5, 1.0]))]
          .round(3).to_string())


if __name__ == "__main__":
    main()
