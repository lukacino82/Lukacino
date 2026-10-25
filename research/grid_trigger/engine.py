"""Move-triggered grid engine: open a trade every time ES moves X points, each trade with its own TP/SL.

Price path: 1-minute bars of ES (back-adjusted, 2011-01 .. 2026-09) walked tick by tick (0.25 point).
Inside a bar the path is O -> L -> H -> C for an up bar (C >= O) and O -> H -> L -> C for a down bar
(alt=1 reverses this, alt=2 visits the extreme nearer to the open first; both are robustness checks). The step from the previous close to the open is a jump:
stops and targets crossed by a jump are filled at the new price.

Trigger: renko logic. The anchor is the price of the last event; price at anchor - X is a 'down' event,
anchor + X an 'up' event, and the anchor moves to that price. Rules map events to trades:
  on_down / on_up = 0 nothing, 1 open long, -1 open short, 2 random side (null model).
  fade long  = down -> long        momentum long  = up -> long
  fade short = up -> short         momentum short = down -> short
Every trade: entry at the trigger price, SL and TP in ticks, closed at the first touch. At most nmax trades open
at once (events beyond the cap are skipped). With flatten=True all trades are closed at the last close of the
Globex day (16:59 ET). X, SL and TP are given per Globex day (constant in points mode, scaled by ATR in ATR mode).
Results are gross (no cost); costs are subtracted per trade afterwards.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from numba import njit, prange

DATA = "/tmp/claude-0/data"
CACHE = os.path.join(DATA, "grid")
START = "2011-01-01"
MAXPOS = 256


def load():
    p = os.path.join(CACHE, "bars.npz")
    if os.path.exists(p):
        z = np.load(p, allow_pickle=True)
        return {k: z[k] for k in z.files}
    d = pd.read_parquet(os.path.join(DATA, "rrr", "bars.parquet"))
    d = d[d.ts >= "2010-09-01"].reset_index(drop=True)
    days = np.unique(d.gday.to_numpy())
    di = np.searchsorted(days, d.gday.to_numpy()).astype(np.int32)
    last = np.r_[di[1:] != di[:-1], True]
    # daily ATR14 (Globex day), known before the day starts, in points
    g = d.groupby("gday").agg(H=("High", "max"), L=("Low", "min"), C=("Close", "last"))
    tr = np.maximum(g.H - g.L, np.maximum((g.H - g.C.shift()).abs(), (g.L - g.C.shift()).abs()))
    atr_d = tr.rolling(14).mean().shift(1).to_numpy()
    # hourly ATR14 averaged over the previous day, in points
    h = d.set_index("ts").resample("1h").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    trh = np.maximum(h.High - h.Low, np.maximum((h.High - h.Close.shift()).abs(), (h.Low - h.Close.shift()).abs()))
    hd = (trh.index + pd.Timedelta(hours=6)).normalize()
    atr_h = trh.groupby(hd).mean().reindex(days).shift(1).to_numpy()
    # weekly ATR14 (weeks ending Friday), known at the start of the week
    w = g.resample("W-FRI").agg({"H": "max", "L": "min", "C": "last"}).dropna()
    trw = np.maximum(w.H - w.L, np.maximum((w.H - w.C.shift()).abs(), (w.L - w.C.shift()).abs()))
    atr_w_s = trw.rolling(14).mean().shift(1)
    wk = pd.DatetimeIndex(days) + pd.to_timedelta((4 - pd.DatetimeIndex(days).weekday) % 7, unit="D")
    atr_w = atr_w_s.reindex(wk).to_numpy()
    out = dict(ts=d.ts.to_numpy(), O=(d.Open.to_numpy() * 4).round().astype(np.int32),
               H=(d.High.to_numpy() * 4).round().astype(np.int32), L=(d.Low.to_numpy() * 4).round().astype(np.int32),
               C=(d.Close.to_numpy() * 4).round().astype(np.int32), di=di, last=last, days=days,
               atr_d=atr_d, atr_h=atr_h, atr_w=atr_w, vol=d.Volume.to_numpy().astype(np.float64))
    os.makedirs(CACHE, exist_ok=True)
    np.savez(p, **out)
    return out


@njit(cache=True)
def _recalc(npos, side, sl, tp):
    hi = 1 << 30; lo = -(1 << 30)
    for k in range(npos):
        if side[k] == 1:
            if tp[k] < hi: hi = tp[k]
            if sl[k] > lo: lo = sl[k]
        else:
            if sl[k] < hi: hi = sl[k]
            if tp[k] > lo: lo = tp[k]
    return hi, lo


@njit(cache=True)
def simulate(O, H, L, C, di, last, ok, X, SL, TP, allowL, allowS, on_down, on_up, nmax, flatten, alt, seed,
             nd, d0):
    """returns per-day gross pnl (ticks), per-day trade count, counts [tp, sl, time], max open, max SL streak"""
    np.random.seed(seed)
    side = np.zeros(MAXPOS, np.int8); ent = np.zeros(MAXPOS, np.int32)
    slv = np.zeros(MAXPOS, np.int32); tpv = np.zeros(MAXPOS, np.int32)
    dp = np.zeros(nd); dn = np.zeros(nd, np.int32); cnt = np.zeros(3, np.int64)
    npos = 0; hi = 1 << 30; lo = -(1 << 30)
    anchor = O[0]; prev = O[0]; maxopen = 0; streak = 0; maxstreak = 0
    pts = np.zeros(4, np.int32)
    for i in range(len(O)):
        d = di[i] - d0
        x = X[di[i]]; s = SL[di[i]]; t = TP[di[i]]
        if C[i] >= O[i]:
            pts[0] = O[i]; pts[1] = L[i]; pts[2] = H[i]; pts[3] = C[i]
        else:
            pts[0] = O[i]; pts[1] = H[i]; pts[2] = L[i]; pts[3] = C[i]
        if alt == 1:
            a1 = pts[1]; pts[1] = pts[2]; pts[2] = a1
        elif alt == 2:                                   # nearest extreme first
            if O[i] - L[i] <= H[i] - O[i]:
                pts[1] = L[i]; pts[2] = H[i]
            else:
                pts[1] = H[i]; pts[2] = L[i]
        cur = prev
        for leg in range(4):
            tgt = pts[leg]
            jump = leg == 0
            while cur != tgt:
                if jump:
                    cur = tgt
                elif tgt > cur:
                    cur += 1
                else:
                    cur -= 1
                p = cur
                # exits
                if npos > 0 and (p >= hi or p <= lo):
                    k = 0
                    while k < npos:
                        hit = 0
                        if side[k] == 1:
                            if p >= tpv[k]: hit = 1
                            elif p <= slv[k]: hit = 2
                        else:
                            if p <= tpv[k]: hit = 1
                            elif p >= slv[k]: hit = 2
                        if hit:
                            pnl = (p - ent[k]) * side[k]
                            if d >= 0:
                                dp[d] += pnl; dn[d] += 1; cnt[hit - 1] += 1
                                if hit == 2:
                                    streak += 1
                                    if streak > maxstreak: maxstreak = streak
                                else:
                                    streak = 0
                            npos -= 1
                            side[k] = side[npos]; ent[k] = ent[npos]; slv[k] = slv[npos]; tpv[k] = tpv[npos]
                        else:
                            k += 1
                    hi, lo = _recalc(npos, side, slv, tpv)
                # triggers
                ev = 0
                if p <= anchor - x:
                    ev = -1; anchor = p
                elif p >= anchor + x:
                    ev = 1; anchor = p
                if ev != 0 and ok[i]:
                    r = on_down if ev == -1 else on_up
                    if r == 2:
                        r = 1 if np.random.random() < 0.5 else -1
                    if r != 0 and npos < nmax and npos < MAXPOS and ((r == 1 and allowL[i]) or (r == -1 and allowS[i])):
                        side[npos] = r; ent[npos] = p
                        if r == 1:
                            slv[npos] = p - s; tpv[npos] = p + t
                        else:
                            slv[npos] = p + s; tpv[npos] = p - t
                        npos += 1
                        if npos > maxopen: maxopen = npos
                        hi, lo = _recalc(npos, side, slv, tpv)
        prev = cur
        if flatten and last[i] and npos > 0:
            for k in range(npos):
                pnl = (C[i] - ent[k]) * side[k]
                if d >= 0:
                    dp[d] += pnl; dn[d] += 1; cnt[2] += 1
            npos = 0; hi = 1 << 30; lo = -(1 << 30)
    return dp, dn, cnt, maxopen, maxstreak


@njit(parallel=True, cache=True)
def run_many(O, H, L, C, di, last, ok, Xs, SLs, TPs, allowL, allowS, rules, nmaxs, flatten, alt, nd, d0):
    """Xs/SLs/TPs: [ncfg, ndays] ticks; rules [ncfg, 2]; returns daily pnl/n and summary per config"""
    n = Xs.shape[0]
    DP = np.zeros((n, nd), np.float32); DN = np.zeros((n, nd), np.int32)
    CNT = np.zeros((n, 3), np.int64); MO = np.zeros(n, np.int32); MS = np.zeros(n, np.int32)
    for c in prange(n):
        dp, dn, cnt, mo, ms = simulate(O, H, L, C, di, last, ok, Xs[c], SLs[c], TPs[c], allowL, allowS,
                                       rules[c, 0], rules[c, 1], nmaxs[c], flatten, alt, 1000 + c, nd, d0)
        DP[c] = dp; DN[c] = dn; CNT[c] = cnt; MO[c] = mo; MS[c] = ms
    return DP, DN, CNT, MO, MS
