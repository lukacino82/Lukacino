"""Entry events and the market context at each entry (all known at the signal bar close).

Entry families (signal on a 5-minute bar, entry at the next 1-minute open)
  GRID     every RTH half hour 10:00-15:00, long and short ("no logic" baseline)
  VWAP     first touch of the RTH / weekly / monthly VWAP from above (long) or below (short)
  COMP     first touch of the 5-day composite value-area low (long) / high (short)
  TEST     price comes back to the low (long) / high (short) of the last 6.5 h, 1 day, 5 days;
           carries how many times that zone was already tested
  SWEEP    trades through that low/high by >= 2 ticks and closes back inside (stop run + reclaim)

Context columns
  regime    up (C > MA50 > MA200), corr (MA200 < C < MA50), down (C < MA200, MA50 < MA200), mixed
  dd        drawdown of the prior close from its 252-day high
  rsiD/W/M  RSI(14) of the last completed day / week / month: os < 30, ob > 70, mid
  rsi2      RSI(2) of the prior day: os < 10, ob > 90
  flatD/W/M VWAP slope (day 1 h, week 1 day, month 1 week) in ATR units below its 33rd percentile
  locD/W/M  close vs RTH / weekly / monthly VWAP: below -2 sd, below, above, above +2 sd
  va5       position vs the prior 5-day composite value area: below VAL / inside / above VAH
  bal       prior 5-day range / ATR20: balance (< 2.5), normal, trend (> 4)
  tests     number of earlier entries into the low/high zone in the window (TEST/SWEEP only)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def bucket_rsi(x, lo=30, hi=70):
    return np.where(x < lo, "os", np.where(x > hi, "ob", "mid"))


@njit(cache=True)
def zone_tests(lo_arr, hi_arr, W, tol, side):
    """For each bar: zone = window extreme of the previous W bars (+/- tol).
    touch[k]   current bar enters the zone (or goes beyond it)
    beyond[k]  current bar trades through the extreme by > 0.5 (2 ticks)
    ntest[k]   how many separate entries into the zone happened in the previous W bars."""
    n = len(lo_arr)
    touch = np.zeros(n, np.bool_)
    beyond = np.zeros(n, np.bool_)
    ntest = np.zeros(n, np.int32)
    ext = np.full(n, np.nan)
    for k in range(W + 1, n):
        if side > 0:
            m = 1e18
            for j in range(k - W, k):
                if lo_arr[j] < m:
                    m = lo_arr[j]
            z = m + tol[k]
            cnt = 0
            inside_prev = False
            for j in range(k - W, k):
                ins = lo_arr[j] <= z
                if ins and not inside_prev:
                    cnt += 1
                inside_prev = ins
            touch[k] = lo_arr[k] <= z and lo_arr[k - 1] > z
            beyond[k] = lo_arr[k] < m - 0.5
        else:
            m = -1e18
            for j in range(k - W, k):
                if hi_arr[j] > m:
                    m = hi_arr[j]
            z = m - tol[k]
            cnt = 0
            inside_prev = False
            for j in range(k - W, k):
                ins = hi_arr[j] >= z
                if ins and not inside_prev:
                    cnt += 1
                inside_prev = ins
            touch[k] = hi_arr[k] >= z and hi_arr[k - 1] < z
            beyond[k] = hi_arr[k] > m + 0.5
        ntest[k] = cnt
        ext[k] = m
    return touch, beyond, ntest, ext


def composite_va(D, N=5, binsz=1.0):
    """VAL/VAH/POC of the previous N RTH sessions from 5-min volume spread evenly over each bar's range."""
    T = D.T
    di = D.di
    rth = D.rth
    days = D.days
    per_day = {}
    for k in np.flatnonzero(np.r_[True, di[1:] != di[:-1]]):
        pass
    order = np.argsort(di, kind="stable")
    starts = np.r_[0, np.flatnonzero(np.diff(di) != 0) + 1]
    ends = np.r_[starts[1:], len(di)]
    for s, e in zip(starts, ends):
        idx = np.arange(s, e)
        idx = idx[rth[idx]]
        if len(idx) < 20:
            continue
        lo = np.floor(D.l[idx].min() / binsz); hi = np.ceil(D.h[idx].max() / binsz)
        hist = np.zeros(int(hi - lo) + 1)
        for j in idx:
            a = int(np.floor(D.l[j] / binsz) - lo); b = int(np.ceil(D.h[j] / binsz) - lo)
            hist[a:b + 1] += D.v[j] / (b - a + 1)
        per_day[di[s]] = (lo, hist)
    val = np.full(len(days), np.nan); vah = val.copy(); poc = val.copy()
    keys = sorted(per_day)
    for pos in range(N, len(keys)):
        win = keys[pos - N:pos]
        lo = min(per_day[k][0] for k in win)
        hi = max(per_day[k][0] + len(per_day[k][1]) for k in win)
        H = np.zeros(int(hi - lo) + 1)
        for k in win:
            l0, h_ = per_day[k]
            off = int(l0 - lo)
            H[off:off + len(h_)] += h_
        p = int(np.argmax(H))
        tot = H.sum(); acc = H[p]; a = b = p
        while acc < 0.7 * tot:
            left = H[a - 1] if a > 0 else -1
            right = H[b + 1] if b < len(H) - 1 else -1
            if right >= left:
                b += 1; acc += H[b]
            else:
                a -= 1; acc += H[a]
        d = keys[pos]
        val[d] = (lo + a) * binsz; vah[d] = (lo + b) * binsz; poc[d] = (lo + p) * binsz
    return val, vah, poc


def build_context(D):
    """Per 5-min bar context arrays (dict of numpy arrays)."""
    T = D.T
    di = D.di
    full = lambda s: s.reindex(D.days).to_numpy()[di]
    C = T.C
    ma50, ma200 = C.rolling(50).mean(), C.rolling(200).mean()
    reg = np.where((C > ma50) & (ma50 > ma200), "up", np.where((C > ma200) & (C < ma50), "corr",
                   np.where((C < ma200) & (ma50 < ma200), "down", "mixed")))
    reg = pd.Series(reg, index=T.index).shift().fillna("mixed")
    dd = (C / C.rolling(252, min_periods=60).max() - 1).shift()
    ddb = pd.Series(np.select([dd > -0.03, dd > -0.07, dd > -0.15], ["0-3%", "3-7%", "7-15%"], ">15%"), index=T.index)
    rD = rsi(C, 14).shift()
    wk = C.groupby(T.index.to_period("W-FRI")).last()
    rW = rsi(wk, 14).shift()  # last completed week
    rW = rW.reindex(T.index.to_period("W-FRI")).to_numpy()
    mo = C.groupby(T.index.to_period("M")).last()
    rM = rsi(mo, 14).shift()
    rM = rM.reindex(T.index.to_period("M")).to_numpy()
    r2 = rsi(C, 2).shift()
    rng5 = (T.H.rolling(5).max() - T.L.rolling(5).min()).shift() / T.atr
    bal = np.where(rng5 < 2.5, "balance", np.where(rng5 > 4, "trend", "normal"))
    ctx = {}
    ctx["regime"] = full(reg)
    ctx["dd"] = full(ddb)
    ctx["rsiD"] = full(pd.Series(bucket_rsi(rD.to_numpy()), index=T.index))
    ctx["rsiW"] = full(pd.Series(bucket_rsi(rW), index=T.index))
    ctx["rsiM"] = full(pd.Series(bucket_rsi(rM), index=T.index))
    ctx["rsi2"] = full(pd.Series(bucket_rsi(r2.to_numpy(), 10, 90), index=T.index))
    ctx["bal"] = full(pd.Series(bal, index=T.index))
    atr = full(T.atr)
    ctx["atr"] = atr
    c = D.c
    disc = D.period == "DISC"

    def slope(vw, n):
        s = np.abs(vw - np.r_[np.full(n, np.nan), vw[:-n]]) / atr
        thr = np.nanquantile(s[disc], 0.33)
        return np.where(np.isfinite(s), np.where(s < thr, "flat", "slope"), "na")
    ctx["flatD"] = slope(D.vw_g, 12)
    ctx["flatW"] = slope(D.vw_w, 276)
    ctx["flatM"] = slope(D.vw_m, 1380)

    def loc(vw, sd):
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (c - vw) / sd
        return np.select([z < -2, z < 0, z <= 2, z > 2], ["<-2sd", "below", "above", ">+2sd"], "na")
    ctx["locD"] = np.where(D.rth, loc(D.vw_r, D.sd_r), "na")
    ctx["locW"] = loc(D.vw_w, D.sd_w)
    ctx["locM"] = loc(D.vw_m, D.sd_m)
    val, vah, poc = composite_va(D, 5)
    v5l, v5h = val[di], vah[di]
    ctx["va5"] = np.select([c < v5l, c > v5h, np.isfinite(v5l)], ["below", "above", "inside"], "na")
    ctx["_val5"], ctx["_vah5"] = v5l, v5h
    tod = D.gmin
    ctx["tod"] = np.select([tod < 570 - 30 + 0, tod < 930, tod < 1080, tod < 1320], ["asia", "europe", "ny_am", "ny_pm"], "post")
    return ctx


def build_events(D, ctx, X):
    """Return DataFrame of entry events with 5-min index k, side, family, tests."""
    rows = []
    gmin, rth, di = D.gmin, D.rth, D.di
    n = len(D.o)
    first_in_day = lambda m: _first_per_day(m, di)
    # GRID
    for t in range(600 - 180 + 330 + 0, 1, 1):
        pass
    grid_marks = [930 + 30 * j - 5 for j in range(1, 12)]  # bar ending at 10:00 ... 15:00 (gmin = minutes since 18:00)
    gm_marks = [m for m in grid_marks]
    mask = np.isin(gmin, gm_marks)
    for s in (1, -1):
        idx = np.flatnonzero(mask)
        rows.append(pd.DataFrame({"k": idx, "side": s, "fam": "GRID", "sub": "every 30 min", "tests": -1}))
    # VWAP touches
    c, h, l = D.c, D.h, D.l
    for nm, vw, valid in (("RTH VWAP", D.vw_r, rth), ("weekly VWAP", D.vw_w, np.ones(n, bool)), ("monthly VWAP", D.vw_m, np.ones(n, bool))):
        pvw = np.r_[np.nan, vw[:-1]]
        with np.errstate(invalid="ignore"):
            from_above = (np.r_[np.nan, l[:-1]] > pvw) & (l <= vw) & valid & np.isfinite(vw)
            from_below = (np.r_[np.nan, h[:-1]] < pvw) & (h >= vw) & valid & np.isfinite(vw)
        for s, m in ((1, from_above), (-1, from_below)):
            idx = np.flatnonzero(first_in_day(m & rth))
            rows.append(pd.DataFrame({"k": idx, "side": s, "fam": "VWAP", "sub": nm, "tests": -1}))
    # composite VA edges
    val, vah = ctx["_val5"], ctx["_vah5"]
    with np.errstate(invalid="ignore"):
        at_val = (np.r_[np.nan, l[:-1]] > np.r_[np.nan, val[:-1]]) & (l <= val) & rth
        at_vah = (np.r_[np.nan, h[:-1]] < np.r_[np.nan, vah[:-1]]) & (h >= vah) & rth
    rows.append(pd.DataFrame({"k": np.flatnonzero(first_in_day(at_val)), "side": 1, "fam": "COMP", "sub": "5d VAL", "tests": -1}))
    rows.append(pd.DataFrame({"k": np.flatnonzero(first_in_day(at_vah)), "side": -1, "fam": "COMP", "sub": "5d VAH", "tests": -1}))
    # level tests and sweeps
    tol = np.maximum(0.1 * ctx["atr"], 1.0)
    tol = np.where(np.isfinite(tol), tol, 2.0)
    for W, nm in ((78, "6.5h"), (276, "1 day"), (1380, "5 days")):
        for s in (1, -1):
            touch, beyond, ntest, ext = zone_tests(D.l, D.h, W, tol, s)
            m = touch & rth
            idx = np.flatnonzero(m)
            rows.append(pd.DataFrame({"k": idx, "side": s, "fam": "TEST", "sub": f"{'low' if s > 0 else 'high'} {nm}", "tests": ntest[idx]}))
            with np.errstate(invalid="ignore"):
                rec = beyond & ((c > ext) if s > 0 else (c < ext)) & rth
            idx = np.flatnonzero(rec)
            rows.append(pd.DataFrame({"k": idx, "side": s, "fam": "SWEEP", "sub": f"{'low' if s > 0 else 'high'} {nm}", "tests": ntest[idx]}))
    E = pd.concat(rows, ignore_index=True)
    E = E[(E.k + 1) < n].copy()
    E["i1"] = X.b5[E.k.to_numpy() + 1]
    # keep TEST/SWEEP events at most one per day per (sub, tests bucket) to limit overlap
    E["day"] = di[E.k.to_numpy()]
    for col, arr in ctx.items():
        if not col.startswith("_") and col != "atr":
            E[col] = arr[E.k.to_numpy()]
    E["period"] = D.period[E.k.to_numpy()]
    E = E.sort_values(["k", "fam", "sub", "side"]).reset_index(drop=True)
    return E


def _first_per_day(m, di):
    idx = np.flatnonzero(m)
    out = np.zeros(len(m), bool)
    if len(idx):
        _, f = np.unique(di[idx], return_index=True)
        out[idx[f]] = True
    return out


def horizon_ends(X, E):
    """1-minute end index (exclusive) for EOD and 5-day horizons."""
    gd = X.gday
    days, first = np.unique(gd, return_index=True)
    rthm = (X.gmin >= 930) & (X.gmin < 1320)
    # last RTH 1-minute index per day
    idx = np.flatnonzero(rthm)
    dpos = np.searchsorted(days, gd[idx])
    last = np.full(len(days), -1)
    np.maximum.at(last, dpos, idx)
    # days without an RTH session (holidays) inherit the previous day's RTH close
    last = np.maximum.accumulate(last)
    ent_day = np.searchsorted(days, gd[E.i1.to_numpy()])
    eod = last[ent_day] + 1
    d5 = np.minimum(ent_day + 4, len(days) - 1)
    end5 = last[d5] + 1
    ok = (eod > E.i1.to_numpy()) & (last[ent_day] >= 0)
    return eod, end5, ok
