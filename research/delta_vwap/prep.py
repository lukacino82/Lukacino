"""Shared 1-minute frame for the delta / VWAP / volume-profile research (ES back-adjusted, points, ET).

Columns: O H L C V delta, gday (Globex day, 18:00 ET start), mod (minute of day ET), rth (09:30-16:00),
cd_g / cd_r: cumulative delta from the Globex start / from 09:30 (RTH only),
vwap_d/sd_d: daily VWAP from 18:00 and its volume-weighted standard deviation (typical price, like Sierra),
vwap_r/sd_r: RTH VWAP from 09:30, vwap_w/sd_w weekly (from Sunday 18:00), vwap_m/sd_m monthly (Globex month),
atr: daily ATR14 known before the day. All values at bar i include bar i (use them at the close of bar i).

Event study: forward change from the close of the event bar to a horizon, in ATR, minus the average change over
the same horizon from the same minute of the day in the same year (removes drift and intraday seasonality);
t-statistic clustered by day."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

DATA = "/tmp/claude-0/data"
CACHE = os.path.join(DATA, "dv")
START = "2011-01-01"
SPLIT = pd.Timestamp("2019-01-01")


def _vw(key, tp, v):
    df = pd.DataFrame({"k": key, "pv": tp * v, "p2v": tp * tp * v, "v": v})
    g = df.groupby("k", sort=False)
    cv = g.v.cumsum().to_numpy(); cpv = g.pv.cumsum().to_numpy(); cp2 = g.p2v.cumsum().to_numpy()
    cv = np.where(cv > 0, cv, np.nan)
    vw = cpv / cv
    sd = np.sqrt(np.maximum(cp2 / cv - vw * vw, 0))
    return pd.Series(vw).ffill().to_numpy(), pd.Series(sd).ffill().to_numpy()


def load():
    p = os.path.join(CACHE, "frame.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    d = pd.read_parquet(os.path.join(DATA, "rrr", "bars.parquet"))
    d = d[d.ts >= "2010-11-01"].reset_index(drop=True)
    f = pd.DataFrame({"ts": d.ts, "O": d.Open, "H": d.High, "L": d.Low, "C": d.Close, "V": d.Volume.astype(float),
                      "delta": d.delta.astype(float), "gday": d.gday})
    f["mod"] = f.ts.dt.hour * 60 + f.ts.dt.minute
    f["rth"] = (f["mod"] >= 570) & (f["mod"] < 960)
    f["cd_g"] = f.groupby("gday").delta.cumsum()
    rk = np.where(f.rth, f.gday.astype("int64"), -1)
    f["cd_r"] = np.where(f.rth, pd.Series(np.where(f.rth, f.delta, 0)).groupby(rk).cumsum(), np.nan)
    tp = ((f.H + f.L + f.C) / 3).to_numpy(); v = f.V.to_numpy()
    f["vwap_d"], f["sd_d"] = _vw(f.gday.to_numpy(), tp, v)
    rv = np.where(f.rth, v, 0.0)
    vr, sr = _vw(rk, tp, rv)
    f["vwap_r"] = np.where(f.rth, vr, np.nan); f["sd_r"] = np.where(f.rth, sr, np.nan)
    wk = (f.gday - pd.to_timedelta(f.gday.dt.day_of_week, unit="D")).to_numpy()
    f["vwap_w"], f["sd_w"] = _vw(wk, tp, v)
    mo = f.gday.dt.to_period("M").astype(str).to_numpy()
    f["vwap_m"], f["sd_m"] = _vw(mo, tp, v)
    g = f.groupby("gday").agg(H=("H", "max"), L=("L", "min"), C=("C", "last"))
    tr = np.maximum(g.H - g.L, np.maximum((g.H - g.C.shift()).abs(), (g.L - g.C.shift()).abs()))
    f["atr"] = f.gday.map(tr.rolling(14).mean().shift(1))
    f = f[f.ts >= START].reset_index(drop=True)
    os.makedirs(CACHE, exist_ok=True)
    f.to_parquet(p)
    return f


def horizons(f):
    """index of the horizon bar for every bar: +15 / +60 minutes (same Globex day), RTH close (15:59 bar of the same
    day), next RTH close"""
    n = len(f)
    gd = f.gday.to_numpy(); mod = f["mod"].to_numpy()
    days, dpos = np.unique(gd, return_inverse=True)
    idx = np.arange(n)
    last_of_day = pd.Series(idx).groupby(dpos).max().to_numpy()
    close_bar = pd.Series(np.where((mod <= 959) & (mod >= 570), idx, -1)).groupby(dpos).max().to_numpy()
    out = {}
    for name, k in (("15m", 15), ("60m", 60)):
        j = np.minimum(idx + k, last_of_day[dpos])
        out[name] = j
    out["close"] = np.where(close_bar[dpos] > idx, close_bar[dpos], -1)
    nxt = np.minimum(dpos + 1, len(days) - 1)
    out["next_close"] = np.where(close_bar[nxt] > idx, close_bar[nxt], -1)
    return out


class Study:
    """event study helper"""

    def __init__(self, f):
        self.f = f
        self.C = f.C.to_numpy(); self.atr = f.atr.to_numpy()
        self.H = horizons(f)
        self.year = f.ts.dt.year.to_numpy(); self.mod = f["mod"].to_numpy()
        self.day = f.gday.to_numpy().astype("datetime64[D]").astype(np.int64)
        self.base = {}
        for h, j in self.H.items():
            fw = np.where(j >= 0, (self.C[np.maximum(j, 0)] - self.C) / self.atr, np.nan)
            b = pd.Series(fw).groupby([self.year, self.mod]).transform("mean").to_numpy()
            self.base[h] = (fw, b)

    def run(self, ev, side=1, name=""):
        """ev: bool mask or index array of event bars; side +1 long view, -1 short view.
        returns one row per horizon: n, mean raw (ATR), mean excess, t, hit rate, by period"""
        idx = np.flatnonzero(ev) if ev.dtype == bool else ev
        rows = []
        disc = self.f.ts.to_numpy()[idx] < np.datetime64(SPLIT)
        for h, (fw, b) in self.base.items():
            r = fw[idx] * side; x = (fw[idx] - b[idx]) * side
            ok = np.isfinite(x)
            if ok.sum() < 20:
                continue
            s = pd.Series(x[ok]).groupby(self.day[idx][ok]).mean()
            t = s.mean() / s.std() * np.sqrt(len(s)) if len(s) > 2 and s.std() > 0 else np.nan
            rows.append(dict(udalost=name, smer="long" if side == 1 else "short", horizont=h, n=int(ok.sum()),
                             dnu=len(s), zmena_atr=np.nanmean(r), excess_atr=x[ok].mean(), t=t,
                             p_zisk=(r[ok] > 0).mean(),
                             excess_2011_18=np.nanmean(x[ok & disc]) if (ok & disc).sum() else np.nan,
                             excess_2019_26=np.nanmean(x[ok & ~disc]) if (ok & ~disc).sum() else np.nan))
        return rows


def first_per_day(mask, gday):
    """first True bar of each Globex day"""
    m = mask & ~pd.Series(mask).groupby(gday).cummax().shift(fill_value=False).to_numpy()
    first = pd.Series(mask).groupby(gday).cumsum().to_numpy() == 1
    return mask & first
