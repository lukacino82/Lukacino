"""RRR matrix engine: one 1-minute pass per entry gives the outcome of every SL x RRR combination.

Data: ES 1-min back-adjusted (ES2008), 2011-01 .. 2026-09 (bid/ask volume, i.e. delta, available from 2011).
Point distances are not affected by the back-adjustment.
Entries: every full hour (open of the hh:00 bar), all 23 Globex hours, long and short.
Horizons: 'intraday' = until 16:59 ET of the same Globex day, '5D' = 5 trading days, '20D' = 20 trading days.
Distance modes:
  'points' - SL 6 .. 100 points, TP = SL x RRR;
  'atr'    - SL = k x ATR of the timeframe that matches the horizon (intraday: ATR14 of hourly bars,
             5D: ATR14 of daily bars, 20D: ATR14 of weekly bars, all known before the entry).
Same-bar touch of SL and TP counts as a loss. Trades still open at the horizon are closed at the last close.
Output per entry: first bar offset of every SL threshold and of every TP distance, close at the horizon.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from numba import njit

DATA = "/tmp/claude-0/data"
CACHE = os.path.join(DATA, "rrr")
SL_PTS = np.array([6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100], float)
SL_ATR = np.array([0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0])
RRR = np.array([1, 1.5, 2, 3, 5, 10, 15, 20, 25], float)
HORIZONS = {"intraday": 0, "5D": 4, "20D": 19}
START = "2011-01-01"


def load_bars():
    p = os.path.join(CACHE, "bars.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    d = pd.read_parquet(os.path.join(DATA, "es2008.parquet"))
    d = d[d.ts >= "2010-06-01"].reset_index(drop=True)
    d["delta"] = (d.Ask - d.Bid).astype(np.int64)
    d["gday"] = (d.ts + pd.Timedelta(hours=6)).dt.normalize()          # Globex day: 18:00 ET opens the next day
    os.makedirs(CACHE, exist_ok=True)
    d.to_parquet(p)
    return d


def atr_series(d):
    """ATR14 of hourly, daily (Globex day) and weekly bars, each shifted so it is known at the start of the bar."""
    s = d.set_index("ts")
    out = {}
    for name, rule in (("H1", "1h"), ("D1", None), ("W1", None)):
        if name == "H1":
            b = s.resample(rule).agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
        elif name == "D1":
            b = s.groupby("gday").agg(High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
        else:
            g = s.groupby("gday").agg(High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
            b = g.resample("W-FRI").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
        tr = np.maximum(b.High - b.Low, np.maximum((b.High - b.Close.shift()).abs(), (b.Low - b.Close.shift()).abs()))
        out[name] = tr.rolling(14).mean().shift(1)
    return out


@njit(cache=True)
def scan(O, H, L, C, ent, end, side, slv, tpv, scale):
    n = len(ent); ns = len(slv); nt = len(tpv)
    t_sl = -np.ones((n, ns), np.int32); t_tp = -np.ones((n, nt), np.int32); cl = np.zeros(n)
    for e in range(n):
        i0 = ent[e]; i1 = end[e]; p = O[i0]; sc = scale[e]
        ks = 0; kt = 0
        for t in range(i0, i1 + 1):
            if side == 1:
                fav = (H[t] - p) / sc; adv = (p - L[t]) / sc
            else:
                fav = (p - L[t]) / sc; adv = (H[t] - p) / sc
            while ks < ns and adv >= slv[ks]:
                t_sl[e, ks] = t - i0; ks += 1
            while kt < nt and fav >= tpv[kt]:
                t_tp[e, kt] = t - i0; kt += 1
            if ks == ns and kt == nt:
                break
        cl[e] = (C[i1] - p) * side / sc
    return t_sl, t_tp, cl


def entries(d):
    """entry bars (hh:00) and horizon end bars"""
    m = d.ts.dt.minute.to_numpy() == 0
    idx = np.flatnonzero(m & (d.ts >= START).to_numpy())
    gd = d.gday.to_numpy()
    days = np.unique(gd)
    day_pos = np.searchsorted(days, gd)
    # last bar of each Globex day before 17:00 ET
    last_bar = pd.Series(np.arange(len(d))).groupby(day_pos).max().to_numpy()
    ends = {}
    for h, k in HORIZONS.items():
        tgt = np.minimum(day_pos[idx] + k, len(days) - 1)
        ends[h] = last_bar[tgt]
    keep = ends["20D"] > idx
    return idx[keep], {h: v[keep] for h, v in ends.items()}


def run(mode="points"):
    os.makedirs(CACHE, exist_ok=True)
    d = load_bars()
    O, H, L, C = (d[c].to_numpy(float) for c in ("Open", "High", "Low", "Close"))
    ent, ends = entries(d)
    if mode == "points":
        slv = SL_PTS
        tpv = np.unique(np.round(np.outer(SL_PTS, RRR).ravel(), 4))
        scales = {h: np.ones(len(ent)) for h in HORIZONS}
    else:
        slv = SL_ATR
        tpv = np.unique(np.round(np.outer(SL_ATR, RRR).ravel(), 4))
        A = atr_series(d)
        ts = d.ts.iloc[ent]
        gday = d.gday.iloc[ent]
        sc_h = A["H1"].reindex(ts.dt.floor("h")).to_numpy()
        sc_d = A["D1"].reindex(gday).to_numpy()
        wk = gday + pd.to_timedelta((4 - gday.dt.weekday) % 7, unit="D")       # week label = its Friday
        sc_w = A["W1"].reindex(wk).to_numpy()
        scales = {"intraday": sc_h, "5D": sc_d, "20D": sc_w}
    for h in HORIZONS:
        sc = scales[h]
        ok = np.isfinite(sc) & (sc > 0)
        for side, sname in ((1, "long"), (-1, "short")):
            t_sl, t_tp, cl = scan(O, H, L, C, ent[ok], ends[h][ok], side, slv, tpv, sc[ok])
            np.savez_compressed(os.path.join(CACHE, f"{mode}_{h}_{sname}.npz"), ent=ent[ok], end=ends[h][ok],
                                t_sl=t_sl, t_tp=t_tp, cl=cl, slv=slv, tpv=tpv, scale=sc[ok])
            print(mode, h, sname, len(cl), flush=True)


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "points")
