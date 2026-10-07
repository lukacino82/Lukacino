"""Systematic families beyond the video, all on ES2008 and all expressed as daily % returns of
1x notional (pnl points / prior RTH close), so 2008 and 2026 are comparable.

  overnight / intraday split        long 16:00 -> 09:30 vs 09:30 -> 16:00
  hour-of-day bias, walk-forward    Mattia's second video, hours picked only from the past
  intraday momentum                 Gao, Han, Li, Zhou (2018): first half hour -> last half hour
  noise-area momentum               Zarattini, Aziz, Barbon (2024) "Beat the Market"
  calendar                          turn of month, pre-holiday, pre-FOMC (2016+), OPEX week
  daily mean reversion              IBS < 0.2 in bull regime (Connors-style)
  exposure overlays                 vol-managed B&H, MA200 trend filter, drawdown-scaled exposure
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from base import Bars

FOMC_2016 = """2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16""".split()

COST = 0.5  # points per round trip


class Grid:
    """Per-day price marks taken from 1-minute bars."""

    def __init__(self, B: Bars):
        self.B = B
        D = B.D
        days = D.index
        self.days = days
        n = len(days)
        # RTH half-hour marks 09:30 .. 16:00 (14 marks: open of each half hour, last = RTH close)
        P = np.full((n, 14), np.nan)
        # hourly marks across the globex day: 18:00(prev) .. 17:00 -> 24 marks
        Hm = np.full((n, 24), np.nan)
        V = np.full((n, 14), np.nan)  # RTH VWAP at the half-hour marks
        for k, d in enumerate(days):
            i = B.dpos[d]
            s, e = B.first[i], B.last[i]
            m = B.mins[s:e]
            cal = B.same[s:e]
            # globex-relative minute: 18:00 prev day = 0
            g = np.where(cal, m + 6 * 60, m - 18 * 60)
            for hh in range(24):
                j = np.searchsorted(g, hh * 60)
                if j < len(g) and g[j] < hh * 60 + 30:
                    Hm[k, hh] = B.o[s + j]
            rs, re_ = B.window(i, 570, 960)
            if re_ - rs < 300:
                continue
            mm = B.mins[rs:re_]
            tp = (B.h[rs:re_] + B.l[rs:re_] + B.c[rs:re_]) / 3
            vv = np.maximum(B.v[rs:re_], 1e-9)
            vw = np.cumsum(tp * vv) / np.cumsum(vv)
            for q in range(13):
                j = np.searchsorted(mm, 570 + 30 * q)
                if j < len(mm):
                    P[k, q] = B.o[rs + j]
                    V[k, q] = vw[j - 1] if j > 0 else B.o[rs]
            P[k, 13] = B.c[re_ - 1]
            V[k, 13] = vw[-1]
        self.P, self.Hm, self.V = P, Hm, V
        self.O = P[:, 0]
        self.C = P[:, 13]
        self.pC = np.r_[np.nan, self.C[:-1]]
        self.H = D.rH.to_numpy(); self.L = D.rL.to_numpy()
        self.bull = D.bull.to_numpy(bool)


# ------------------------------------------------------------------ helpers
def series(G, pts, days_mask=None):
    """points pnl per day (nan = flat) -> daily % return on 1x notional of the prior close."""
    r = pts / G.pC
    r = np.where(np.isfinite(r), r, 0.0)
    return pd.Series(r, index=G.days)


def bh(G):
    return pd.Series(np.nan_to_num(G.C / G.pC - 1), index=G.days)


# ------------------------------------------------------------------ families
def overnight(G, cost=COST):
    """long from RTH close (16:00) to next RTH open, i.e. the overnight/globex session."""
    pts = G.O - G.pC - cost
    return series(G, pts)


def rth_only(G, cost=COST):
    return series(G, G.C - G.O - cost)


def hour_bias_wf(G, lookback=5, top=6, bottom=2, start=2011, cost=COST):
    """Each year: long the `top` best hours and short the `bottom` worst hours of the past
    `lookback` years (hour returns of the globex day, hour h = open(h) -> open(h+1))."""
    Hm = G.Hm
    hr = Hm[:, 1:] / Hm[:, :-1] - 1  # 23 hourly returns
    pts_h = Hm[:, 1:] - Hm[:, :-1]
    years = G.days.year.to_numpy()
    out = np.zeros(len(G.days))
    picks = {}
    for y in range(start, years.max() + 1):
        past = (years >= y - lookback) & (years < y)
        cur = years == y
        mu = np.nanmean(hr[past], 0)
        order = np.argsort(mu)
        longs = [h for h in order[::-1][:top] if mu[h] > 0]
        shorts = [h for h in order[:bottom] if mu[h] < 0]
        picks[y] = (longs, shorts)
        p = np.nansum(pts_h[cur][:, longs], 1) - np.nansum(pts_h[cur][:, shorts], 1)
        # one round trip per contiguous block of hours with the same position
        posv = np.zeros(23)
        posv[longs] = 1
        posv[shorts] = -1
        blocks = sum(1 for h in range(23) if posv[h] != 0 and (h == 0 or posv[h - 1] != posv[h]))
        out[cur] = p - cost * blocks
    r = out / G.pC
    r[~np.isfinite(r)] = 0
    s = pd.Series(r, index=G.days)
    return s[G.days.year >= start], picks


def hour_table(G):
    hr = G.Hm[:, 1:] / G.Hm[:, :-1] - 1
    lab = [f"{(18 + h) % 24:02d}:00" for h in range(23)]
    df = pd.DataFrame(hr, index=G.days, columns=lab)
    return df


def intraday_momentum(G, last_q=12):
    """sign(prev close -> 10:00) traded from 15:30 to 16:00 (Gao et al. 2018)."""
    r1 = G.P[:, 1] / G.pC - 1
    sgn = np.sign(r1)
    pts = sgn * (G.C - G.P[:, last_q]) - COST * (sgn != 0)
    return series(G, pts)


def noise_momentum(G, lookback=14, start_q=1, both=True, vm=1.0, cost=COST):
    """Zarattini-Aziz-Barbon noise area. Checks every half hour from 10:00, trail stop at
    max(boundary, VWAP), flat at the close. Returns daily % and trade count."""
    P, V = G.P, G.V
    O = G.O
    move = np.abs(P / O[:, None] - 1)
    sig = pd.DataFrame(move).rolling(lookback).mean().shift().to_numpy() * vm
    up_ref = np.maximum(O, G.pC)
    dn_ref = np.minimum(O, G.pC)
    n = len(G.days)
    pts = np.zeros(n)
    ntrades = 0
    for d in range(n):
        if not np.isfinite(sig[d, start_q]) or not np.isfinite(G.pC[d]) or np.isnan(P[d]).any():
            continue
        pos, ent = 0, 0.0
        for q in range(start_q, 13):
            px = P[d, q]
            ub = up_ref[d] * (1 + sig[d, q]); lb = dn_ref[d] * (1 - sig[d, q])
            if pos > 0 and px < max(ub, V[d, q]):
                pts[d] += px - ent - cost; pos = 0
            elif pos < 0 and px > min(lb, V[d, q]):
                pts[d] += ent - px - cost; pos = 0
            if pos == 0:
                if px > ub:
                    pos, ent = 1, px; ntrades += 1
                elif both and px < lb:
                    pos, ent = -1, px; ntrades += 1
        if pos != 0:
            pts[d] += pos * (G.C[d] - ent) - cost
    return series(G, pts), ntrades


def turn_of_month(G):
    """long from the close of trading day -2 to the close of day +3 of the next month."""
    idx = G.days
    ym = idx.year * 12 + idx.month
    nxt = np.r_[ym[1:], -1]
    last = np.where(ym != nxt)[0]  # last trading day of each month
    hold = np.zeros(len(idx), bool)
    for L in last:
        for k in range(L, min(L + 4, len(idx))):  # returns of days -1 .. +3
            hold[k] = True
    r = np.where(hold, G.C / G.pC - 1 - COST / G.pC, 0.0)
    return pd.Series(np.nan_to_num(r), index=idx)


def pre_holiday(G):
    """long the close-to-close return of the last trading day before a weekday market holiday."""
    idx = G.days
    allbd = pd.bdate_range(idx[0], idx[-1])
    hol = allbd.difference(idx)
    pre = set()
    for h in hol:
        p = idx[idx < h]
        if len(p):
            pre.add(p[-1])
    m = np.array([d in pre for d in idx])
    r = np.where(m, G.C / G.pC - 1 - COST / G.pC, 0.0)
    return pd.Series(np.nan_to_num(r), index=idx)


def pre_fomc(G):
    """long from 14:00 the day before FOMC to 14:00 FOMC day (Lucca & Moench), 2016+ list.
    Approximated with RTH marks: prior day 14:00 mark (q=9) -> FOMC day 14:00 mark."""
    f = set(pd.to_datetime(FOMC_2016))
    idx = G.days
    r = np.zeros(len(idx))
    for k in range(1, len(idx)):
        if idx[k] in f:
            pts = G.P[k, 9] - G.P[k - 1, 9] - COST
            r[k] = pts / G.pC[k] if np.isfinite(pts) else 0
    s = pd.Series(r, index=idx)
    return s[idx >= "2016-07-01"]


def opex_week(G):
    """long close-to-close during the week of the monthly option expiry (3rd Friday)."""
    idx = G.days
    third_fri = set()
    for y in range(idx[0].year, idx[-1].year + 1):
        for mth in range(1, 13):
            d = pd.Timestamp(y, mth, 15)
            third_fri.add(d + pd.Timedelta(days=(4 - d.dayofweek) % 7))
    wk = np.array([(d + pd.Timedelta(days=(4 - d.dayofweek) % 7)) in third_fri for d in idx])
    r = np.where(wk, G.C / G.pC - 1, 0.0)
    return pd.Series(np.nan_to_num(r), index=idx)


def ibs_bull(G, thr=0.2):
    """IBS = (C-L)/(H-L) of the RTH day; long next close-to-close if IBS < thr and bull200."""
    ibs = (G.C - G.L) / np.maximum(G.H - G.L, 0.25)
    sig = (ibs < thr) & G.bull
    sig = np.r_[False, sig[:-1]]
    r = np.where(sig, G.C / G.pC - 1 - COST / G.pC, 0.0)
    return pd.Series(np.nan_to_num(r), index=G.days)


def exposure_overlays(G):
    """Return dict of daily % series with variable exposure on the close-to-close return."""
    ret = G.C / G.pC - 1
    ret = np.nan_to_num(ret)
    s = pd.Series(ret, index=G.days)
    rv = s.rolling(20).std().shift() * np.sqrt(252)
    out = {}
    target = s.std() * np.sqrt(252)
    w_vol = (target / rv).clip(0, 2.0).fillna(1.0)
    out["Vol-managed B&H (cap 2x)"] = (w_vol, s)
    cl = pd.Series(G.C, index=G.days).ffill()
    ma = cl.rolling(200).mean()
    w_trend = (cl > ma).shift().fillna(True).astype(float)
    out["Trend filter MA200 (0/1)"] = (w_trend, s)
    peak = pd.Series(G.C, index=G.days).cummax()
    dd = (pd.Series(G.C, index=G.days) / peak - 1).shift().fillna(0)
    bull = pd.Series(G.bull, index=G.days)
    w_dd = (1 + ((dd <= -0.05) & bull).astype(float) * 0.5 + ((dd <= -0.10) & bull).astype(float) * 0.5)
    out["Drawdown add-on in bull (1-2x)"] = (w_dd, s)
    return out


def crisis_allocator(G, dd_thr=-0.03, ll=3, layer=0.8, hold=60, max_layers=4, arm_days=20):
    """Approximation of the ChatGPT 'crisis allocator': 1x core; when drawdown from ATH <= dd_thr,
    `ll` consecutive lower lows and a bull structure (MA50 > MA200, MA200 rising), every later
    prior-day-low reclaim adds a `layer`x position held `hold` days (max `max_layers`).
    Returns the daily exposure series (applied to the next day's return)."""
    C = pd.Series(G.C, index=G.days).ffill()
    L = pd.Series(G.L, index=G.days).ffill()
    ath = C.cummax()
    dd = C / ath - 1
    lower = (L < L.shift())
    llrun = lower.rolling(ll).sum() == ll
    ma50, ma200 = C.rolling(50).mean(), C.rolling(200).mean()
    bull = (ma50 > ma200) & (ma200 > ma200.shift(20))
    armed_evt = (dd <= dd_thr) & llrun & bull
    reclaim = (L < L.shift()) & (C > L.shift())
    n = len(C)
    w = np.ones(n)
    layers = []  # expiry indices
    armed_until = -1
    for t in range(n):
        layers = [x for x in layers if x > t]
        if armed_evt.iloc[t]:
            armed_until = t + arm_days
        if t <= armed_until and reclaim.iloc[t] and len(layers) < max_layers:
            layers.append(t + hold)
        w[t] = 1 + layer * len(layers)
    return pd.Series(w, index=G.days)
