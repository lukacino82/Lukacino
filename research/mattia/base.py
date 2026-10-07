"""Shared data layer for the Mattia strategy tests on ES2008 (1-minute, back-adjusted, ET).

Clock conventions: the source file is US/Eastern. Mattia quotes Central time, so
midnight CT = 01:00 ET, 08:30 CT = 09:30 ET, 10:00 CT = 11:00 ET, 14:30 CT = 15:30 ET.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

DATA = "/tmp/claude-0/data/es2008.parquet"
PERIODS = [("PRE 2008-17", "2008-01-01", "2017-12-31"),   # never seen by the video's research
           ("IS 2018-22", "2018-01-01", "2022-12-31"),    # Mattia's in-sample
           ("OOS 2023-26", "2023-01-01", "2026-12-31")]   # Mattia's out-of-sample
COST = 0.5  # ES points per round trip (commission + 1 tick slippage)
PT = 50.0   # USD per ES point


class Bars:
    def __init__(self, path=DATA):
        df = pd.read_parquet(path)
        ts = df.ts
        self.ts = ts.to_numpy()
        self.o = df.Open.to_numpy(float); self.h = df.High.to_numpy(float)
        self.l = df.Low.to_numpy(float); self.c = df.Close.to_numpy(float)
        self.v = df.Volume.to_numpy(float)
        self.dl = (df.Ask - df.Bid).to_numpy(float)
        self.mins = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
        d = ts.dt.normalize()
        gday = d.where(ts.dt.hour < 18, d + pd.Timedelta(days=1))
        wd = gday.dt.dayofweek
        gday = gday.where(wd != 5, gday + pd.Timedelta(days=2)).where(wd != 6, gday + pd.Timedelta(days=1))
        self.gday = gday.to_numpy()
        # calendar day == globex day for bars from 00:00 to 17:59
        self.same = (ts.dt.normalize().to_numpy() == self.gday)
        u, first = np.unique(self.gday, return_index=True)
        last = np.r_[first[1:], len(df)]
        self.days = pd.DatetimeIndex(u)
        self.first, self.last = first, last  # index range of each globex day
        self._daily()

    def window(self, i, a, b):
        """raw index range [s, e) of day i with clock minutes in [a, b) on the calendar day."""
        s, e = self.first[i], self.last[i]
        m = self.mins[s:e]
        cal = self.same[s:e]
        idx = np.where(cal & (m >= a) & (m < b))[0]
        if len(idx) == 0:
            return s, s
        return s + idx[0], s + idx[-1] + 1

    def _daily(self):
        """Mattia session = midnight CT (01:00 ET) .. 16:00 CT (17:00 ET); RTH = 09:30-16:00 ET."""
        n = len(self.days)
        H = np.full(n, np.nan); L = H.copy(); C = H.copy(); O = H.copy()
        rO = H.copy(); rH = H.copy(); rL = H.copy(); rC = H.copy()
        for i in range(n):
            s, e = self.window(i, 60, 17 * 60)
            if e - s > 30:
                O[i] = self.o[s]; H[i] = self.h[s:e].max(); L[i] = self.l[s:e].min(); C[i] = self.c[e - 1]
            s, e = self.window(i, 570, 960)
            if e - s > 30:
                rO[i] = self.o[s]; rH[i] = self.h[s:e].max(); rL[i] = self.l[s:e].min(); rC[i] = self.c[e - 1]
        D = pd.DataFrame(dict(O=O, H=H, L=L, C=C, rO=rO, rH=rH, rL=rL, rC=rC), index=self.days)
        ok = D.C.notna() & D.rC.notna()
        D = D[ok]
        pc = D.C.shift()
        tr = np.maximum(D.H - D.L, np.maximum((D.H - pc).abs(), (D.L - pc).abs()))
        D["atr15"] = tr.rolling(15).mean().shift()          # known at midnight CT
        rpc = D.rC.shift()
        rtr = np.maximum(D.rH - D.rL, np.maximum((D.rH - rpc).abs(), (D.rL - rpc).abs()))
        D["ratr14"] = rtr.rolling(14).mean().shift()
        D["ma200"] = D.rC.rolling(200).mean().shift()
        D["bull"] = D.rC.shift() > D.ma200
        self.D = D
        self.dpos = {d: k for k, d in enumerate(self.days)}


def resample_day(B: Bars, s, e, n):
    """Clock-aligned n-minute bars from raw range [s, e). Returns arrays and the raw index of
    the first bar after each bucket (entry bar)."""
    m = B.mins[s:e]
    k = (m // n)
    brk = np.r_[0, np.where(np.diff(k) != 0)[0] + 1, len(k)]
    out = []
    for a, b in zip(brk[:-1], brk[1:]):
        out.append((k[a] * n, B.o[s + a], B.h[s + a:s + b].max(), B.l[s + a:s + b].min(), B.c[s + b - 1],
                    B.v[s + a:s + b].sum(), s + b))
    return np.array(out, dtype=float).reshape(-1, 7)


def wilder_adx(h, l, c, n=14):
    """Wilder ADX on a continuous bar series."""
    up = np.r_[0, h[1:] - h[:-1]]
    dn = np.r_[0, l[:-1] - l[1:]]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = 1.0 / n
    atr = pd.Series(tr).ewm(alpha=a, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=a, adjust=False).mean().to_numpy() / atr
    ndi = 100 * pd.Series(ndm).ewm(alpha=a, adjust=False).mean().to_numpy() / atr
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    return pd.Series(dx).ewm(alpha=a, adjust=False).mean().to_numpy()


@njit(cache=True)
def run_exit(o, h, l, c, i0, end, side, tp, sl):
    """Market entry at o[i0]; tp/sl are absolute prices (nan = none). SL first in one bar.
    Exit at close of end-1 if neither hits. Returns entry, exit price, exit index, code."""
    e = o[i0]
    for k in range(i0, end):
        if side > 0:
            if not np.isnan(sl) and l[k] <= sl:
                return e, min(sl, o[k]), k, -1
            if not np.isnan(tp) and h[k] >= tp:
                return e, max(tp, o[k]) if k > i0 else tp, k, 1
        else:
            if not np.isnan(sl) and h[k] >= sl:
                return e, max(sl, o[k]), k, -1
            if not np.isnan(tp) and l[k] <= tp:
                return e, min(tp, o[k]) if k > i0 else tp, k, 1
    return e, c[end - 1], end - 1, 0


def period(d):
    for name, a, b in PERIODS:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return name
    return None


def summarize(tr: pd.DataFrame, cost=COST):
    """tr has columns date, pnl (gross points)."""
    out = {}
    for name in ["ALL"] + [p for p, _, _ in PERIODS]:
        t = tr if name == "ALL" else tr[tr.period == name]
        p = t.pnl.to_numpy() - cost
        if len(p) == 0:
            out[name] = dict(n=0)
            continue
        eq = np.cumsum(p)
        dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        g, ls = p[p > 0].sum(), -p[p < 0].sum()
        out[name] = dict(n=len(p), exp=p.mean(), win=(p > 0).mean(), pf=g / ls if ls else np.inf, net=eq[-1], maxdd=dd,
                         t=p.mean() / p.std(ddof=1) * np.sqrt(len(p)) if len(p) > 2 else np.nan)
    return out
