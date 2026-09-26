"""Backtest engine for ES intraday research.

Works on any bar source with columns ts, Open, High, Low, Close, Volume, Bid, Ask:
  * ES3000.txt  - 1-minute bars, 2018-07 .. 2026-09 (unadjusted continuous contract)
  * Excel List1 - 5000-contract volume bars, 2016-07 .. 2026-07 (back-adjusted)

Execution contract (identical for every strategy, taken from codex_astra_strategy_spec.json):
  signal on a completed 5-minute RTH bucket, entry at the open of the next source bar,
  TP/SL checked bar by bar with SL first when both are touched in one bar,
  time stop 120 minutes and hard exit at the 16:00 close, one trade per strategy per day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

RTH_START = 9 * 60 + 30
RTH_END = 16 * 60
NBUCKET = (RTH_END - RTH_START) // 5  # 78 five-minute buckets


# --------------------------------------------------------------------------- data
def load_bars(path: str) -> pd.DataFrame:
    return pd.read_parquet(path).sort_values("ts").reset_index(drop=True)


def daily_adjusted(vol_daily: pd.DataFrame, m1_daily: pd.DataFrame) -> pd.DataFrame:
    """Back-adjusted RTH daily OHLC: Excel (back-adjusted) history, extended with
    ES3000 days after the Excel file ends, shifted by the last observed offset."""
    a = vol_daily[["O", "H", "L", "C"]].copy()
    b = m1_daily[["O", "H", "L", "C"]].copy()
    common = a.index.intersection(b.index)[-10:]
    off = float(np.median(a.loc[common, "C"] - b.loc[common, "C"]))
    ext = b.loc[b.index > a.index[-1]] + off
    out = pd.concat([a, ext])
    out.index = pd.DatetimeIndex(out.index)
    return out


def trading_day(ts: pd.Series) -> pd.Series:
    """Globex trading day: bars from 18:00 belong to the next calendar day."""
    d = ts.dt.normalize()
    d = d.where(ts.dt.hour < 18, d + pd.Timedelta(days=1))
    # Friday 18:00+ does not exist; Saturday -> Monday
    wd = d.dt.dayofweek
    d = d.where(wd != 5, d + pd.Timedelta(days=2))
    d = d.where(wd != 6, d + pd.Timedelta(days=1))
    return d


# ---------------------------------------------------------------- TPO profile
def tpo_profile(highs, lows, tick=0.25):
    """Prior-day TPO profile from 30-minute period highs/lows. Returns POC, VAH, VAL."""
    lo = np.floor(np.min(lows) / tick)
    hi = np.ceil(np.max(highs) / tick)
    n = int(hi - lo) + 1
    cnt = np.zeros(n)
    for h, l in zip(highs, lows):
        a = int(np.floor(l / tick) - lo)
        b = int(np.ceil(h / tick) - lo)
        cnt[a:b + 1] += 1
    prices = (np.arange(n) + lo) * tick
    mx = cnt.max()
    cand = np.where(cnt == mx)[0]
    mid = (prices[0] + prices[-1]) / 2
    poc_i = cand[np.lexsort((prices[cand], np.abs(prices[cand] - mid)))[0]]
    order = np.lexsort((np.abs(prices - prices[poc_i]), -cnt))
    tot = cnt.sum()
    cum = np.cumsum(cnt[order])
    k = int(np.searchsorted(cum, 0.7 * tot)) + 1
    sel = prices[order[:k]]
    return prices[poc_i], sel.max(), sel.min()


# ------------------------------------------------------------------ sessions
class Sessions:
    """Per-RTH-day arrays: 5-minute buckets + index ranges into the raw bar arrays."""

    def __init__(self, bars: pd.DataFrame, daily_adj: pd.DataFrame | None = None):
        ts = bars.ts
        self.o = bars.Open.to_numpy(float)
        self.h = bars.High.to_numpy(float)
        self.l = bars.Low.to_numpy(float)
        self.c = bars.Close.to_numpy(float)
        self.v = bars.Volume.to_numpy(float)
        self.dl = (bars.Ask - bars.Bid).to_numpy(float)
        tday = trading_day(ts)
        mins = (ts.dt.hour * 60 + ts.dt.minute + ts.dt.second / 60).to_numpy()
        self.mins = mins
        rth = (mins >= RTH_START) & (mins < RTH_END) & (ts.dt.normalize() == tday).to_numpy()
        self.rth = rth
        days = tday.to_numpy()
        # RTH index ranges
        idx = np.where(rth)[0]
        rd = days[idx]
        brk = np.r_[0, np.where(rd[1:] != rd[:-1])[0] + 1, len(idx)]
        self.dates = []
        self.rs, self.re = [], []  # rth start/end (exclusive) indices into raw arrays
        for a, b in zip(brk[:-1], brk[1:]):
            if b - a < 20:
                continue
            self.dates.append(pd.Timestamp(rd[a]))
            self.rs.append(idx[a])
            self.re.append(idx[b - 1] + 1)
        self.dates = pd.DatetimeIndex(self.dates)
        self.rs = np.array(self.rs)
        self.re = np.array(self.re)
        nd = len(self.dates)
        # overnight range: bars of same trading day before RTH start
        day_first = {}
        uniq, first = np.unique(days, return_index=True)
        for u, f in zip(uniq, first):
            day_first[pd.Timestamp(u)] = f
        self.onh = np.full(nd, np.nan)
        self.onl = np.full(nd, np.nan)
        for i, d in enumerate(self.dates):
            f = day_first.get(d)
            if f is not None and f < self.rs[i]:
                self.onh[i] = self.h[f:self.rs[i]].max()
                self.onl[i] = self.l[f:self.rs[i]].min()
        self._build_buckets()
        self._build_daily(daily_adj)

    # 5-minute buckets --------------------------------------------------------
    def _build_buckets(self):
        nd = len(self.dates)
        B = NBUCKET
        O = np.full((nd, B), np.nan); H = O.copy(); L = O.copy(); C = O.copy()
        V = np.zeros((nd, B)); D = np.zeros((nd, B))
        nxt = np.full((nd, B), -1, dtype=np.int64)  # raw index of first bar after bucket end
        for i in range(nd):
            a, b = self.rs[i], self.re[i]
            k = ((self.mins[a:b] - RTH_START) // 5).astype(int)
            for j in range(B):
                m = k == j
                if not m.any():
                    continue
                s = np.where(m)[0] + a
                O[i, j] = self.o[s[0]]; C[i, j] = self.c[s[-1]]
                H[i, j] = self.h[s].max(); L[i, j] = self.l[s].min()
                V[i, j] = self.v[s].sum(); D[i, j] = self.dl[s].sum()
            # first bar whose start >= bucket end
            ends = RTH_START + 5 * (np.arange(B) + 1)
            pos = np.searchsorted(self.mins[a:b], ends - 1e-9)
            nxt[i] = np.where(pos < b - a, pos + a, -1)
        # forward fill empty buckets (volume bars can skip a bucket)
        for arr in (C,):
            df = pd.DataFrame(arr).ffill(axis=1)
            arr[:] = df.to_numpy()
        for arr in (O, H, L):
            arr[:] = np.where(np.isnan(arr), C, arr)
        self.O5, self.H5, self.L5, self.C5, self.V5, self.D5, self.nxt = O, H, L, C, V, D, nxt
        tp = (H + L + C) / 3
        cv = np.cumsum(V, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.vwap = np.cumsum(tp * V, 1) / cv
            var = np.maximum(np.cumsum(tp * tp * V, 1) / cv - self.vwap ** 2, 0)
            self.vwap_z = (C - self.vwap) / np.sqrt(var)
        self.vwap_z[~np.isfinite(self.vwap_z)] = 0
        self.cd = np.cumsum(D, 1)

    # daily table -------------------------------------------------------------
    def _build_daily(self, daily_adj):
        nd = len(self.dates)
        dO = np.array([self.o[a] for a in self.rs])
        dH = np.array([self.h[a:b].max() for a, b in zip(self.rs, self.re)])
        dL = np.array([self.l[a:b].min() for a, b in zip(self.rs, self.re)])
        dC = np.array([self.c[b - 1] for b in self.re])
        self.dO, self.dH, self.dL, self.dC = dO, dH, dL, dC
        # prior-day TPO profile on the raw (same-contract) prices
        self.poc = np.full(nd, np.nan); self.vah = self.poc.copy(); self.val = self.poc.copy()
        for i in range(1, nd):
            j = i - 1
            H, L = self.H5[j], self.L5[j]
            ph = np.nanmax(H.reshape(-1, 6), 1)
            pl = np.nanmin(L.reshape(-1, 6), 1)
            self.poc[i], self.vah[i], self.val[i] = tpo_profile(ph, pl)
        self.pdl = np.r_[np.nan, dL[:-1]]
        self.pdh = np.r_[np.nan, dH[:-1]]
        self.pdc = np.r_[np.nan, dC[:-1]]
        # regime features from a back-adjusted daily series (no roll gaps)
        if daily_adj is None:
            A = pd.DataFrame({"O": dO, "H": dH, "L": dL, "C": dC}, index=self.dates)
        else:
            A = daily_adj.reindex(self.dates.union(daily_adj.index)).sort_index()
        pc = A.C.shift()
        tr = np.maximum(A.H - A.L, np.maximum((A.H - pc).abs(), (A.L - pc).abs()))
        R = pd.DataFrame(index=A.index)
        R["atr20"] = tr.rolling(20).mean().shift()
        ma200 = A.C.rolling(200).mean()
        R["bull200"] = (A.C > ma200).shift().fillna(False).astype(bool)
        R["ma200_ok"] = ma200.shift().notna()
        R["ath"] = A.H.cummax().shift()
        R["hi252"] = A.H.rolling(252, min_periods=120).max().shift()
        R["pclose_adj"] = A.C.shift()
        R["dd252_prev"] = A.C.shift() / R.hi252 - 1
        down = (A.C < A.C.shift()).astype(int)
        R["down2"] = ((down.shift(1) == 1) & (down.shift(2) == 1))
        R["prev_up"] = (A.C.shift(1) > A.C.shift(2))
        R["gap"] = A.O / A.C.shift() - 1
        R["atr_rank"] = R.atr20.rolling(252, min_periods=60).rank(pct=True)
        R = R.reindex(self.dates)
        self.R = R
        # roll days: the day the raw series switches contract (prior-day levels unusable).
        # Detected as the largest jump of (adjusted - raw) prior close in each roll month.
        off = pd.Series(R.pclose_adj.to_numpy() - self.pdc, index=self.dates)
        step = off.diff().abs()
        self.roll = np.zeros(nd, bool)
        self.roll[0] = True
        for (y, m), g in step.groupby([self.dates.year, self.dates.month]):
            if m in (3, 6, 9, 12):
                g = g[g.index.day <= 21]
                if len(g) and g.max() > 4:
                    self.roll[self.dates.get_loc(g.idxmax())] = True
        self.adj_off = (R.pclose_adj.to_numpy() - self.pdc)  # adjusted - raw (prior close)


# ------------------------------------------------------------- exit simulator
@njit(cache=True)
def simulate(o, h, l, c, mins, entry_idx, end_idx, side, tp, sl, tstop_min):
    """Market entry at o[entry_idx]; TP/SL offsets in points; SL first in same bar.
    end_idx is exclusive (session end). Returns pnl points, exit code (1 TP, -1 SL, 0 time)."""
    n = len(entry_idx)
    pnl = np.zeros(n)
    code = np.zeros(n, np.int8)
    for t in range(n):
        i = entry_idx[t]
        e = o[i]
        s = side[t]
        tpp = e + s * tp[t]
        slp = e - s * sl[t]
        dead = mins[i] + tstop_min
        last = i
        done = False
        for k in range(i, end_idx[t]):
            if mins[k] >= dead and k > i:
                break
            last = k
            if s > 0:
                if l[k] <= slp:
                    pnl[t] = -sl[t]; code[t] = -1; done = True; break
                if h[k] >= tpp:
                    pnl[t] = tp[t]; code[t] = 1; done = True; break
            else:
                if h[k] >= slp:
                    pnl[t] = -sl[t]; code[t] = -1; done = True; break
                if l[k] <= tpp:
                    pnl[t] = tp[t]; code[t] = 1; done = True; break
        if not done:
            pnl[t] = s * (c[last] - e)
    return pnl, code


@njit(cache=True)
def simulate_limit(o, h, l, c, start_idx, end_idx, side, entry_px, tp, sl, fill_dir):
    """Resting limit order at entry_px from start_idx until session end, then TP/SL,
    exit at the session close. In the fill bar only SL (or TP if the close is beyond it)
    counts, which is the conservative reading of an unknown intrabar path.
    fill_dir -1: order fills when price trades down to entry_px (buy limit / sell stop),
    +1: fills when price trades up to entry_px (sell limit / buy stop).
    Returns pnl, filled flag, exit code."""
    n = len(start_idx)
    pnl = np.zeros(n)
    filled = np.zeros(n, np.bool_)
    code = np.zeros(n, np.int8)
    for t in range(n):
        s = side[t]
        px = entry_px[t]
        f = -1
        for k in range(start_idx[t], end_idx[t]):
            if (fill_dir[t] < 0 and l[k] <= px) or (fill_dir[t] > 0 and h[k] >= px):
                f = k
                break
        if f < 0:
            continue
        filled[t] = True
        tpp = px + s * tp[t]
        slp = px - s * sl[t]
        # fill bar
        if (s > 0 and l[f] <= slp) or (s < 0 and h[f] >= slp):
            pnl[t] = -sl[t]; code[t] = -1; continue
        if (s > 0 and c[f] >= tpp) or (s < 0 and c[f] <= tpp):
            pnl[t] = tp[t]; code[t] = 1; continue
        done = False
        for k in range(f + 1, end_idx[t]):
            if s > 0:
                if l[k] <= slp:
                    pnl[t] = -sl[t]; code[t] = -1; done = True; break
                if h[k] >= tpp:
                    pnl[t] = tp[t]; code[t] = 1; done = True; break
            else:
                if h[k] >= slp:
                    pnl[t] = -sl[t]; code[t] = -1; done = True; break
                if l[k] <= tpp:
                    pnl[t] = tp[t]; code[t] = 1; done = True; break
        if not done:
            pnl[t] = s * (c[end_idx[t] - 1] - px)
    return pnl, filled, code


# ------------------------------------------------------------------ metrics
PERIODS = [
    ("PRE 2016-18", "2016-01-01", "2018-07-08"),
    ("DISC 2018-22", "2018-07-09", "2022-12-31"),
    ("VAL 2023-24", "2023-01-01", "2024-12-31"),
    ("OOS 2025-26", "2025-01-01", "2026-12-31"),
]


def period_of(dates: pd.DatetimeIndex) -> np.ndarray:
    out = np.empty(len(dates), dtype=object)
    for name, a, b in PERIODS:
        out[(dates >= a) & (dates <= b)] = name
    return out


def stats(p: np.ndarray) -> dict:
    n = len(p)
    if n == 0:
        return dict(n=0, exp=np.nan, win=np.nan, pf=np.nan, net=0.0, maxdd=0.0, t=np.nan)
    eq = np.cumsum(p)
    dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
    g, ls = p[p > 0].sum(), -p[p < 0].sum()
    sd = p.std(ddof=1) if n > 1 else np.nan
    return dict(n=n, exp=p.mean(), win=(p > 0).mean(), pf=g / ls if ls > 0 else np.inf,
                net=eq[-1], maxdd=dd, t=p.mean() / sd * np.sqrt(n) if sd and sd > 0 else np.nan)
