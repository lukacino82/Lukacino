"""Data layer of the Edge Factory (ES2008, 1-minute, back-adjusted, US/Eastern).

Builds and caches
  5-minute globex bars   o h l c v delta, globex day, minute-of-globex-day (0 = 18:00 ET),
                         RTH / globex / weekly / monthly anchored VWAP and sigma, cumulative delta
  daily table            RTH and globex OHLC, overnight range, volume, delta, ATR, regime,
                         calendar fields (weekday, day of month, trading day of month, OPEX,
                         holidays, FOMC 2016+, lunar phase)
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

SRC = "/tmp/claude-0/data/es2008.parquet"
CACHE = "/tmp/claude-0/data/ef_cache.pkl"

PERIODS = {"DISC": ("2008-01-01", "2016-12-31"), "VAL": ("2017-01-01", "2021-12-31"),
           "TEST": ("2022-01-01", "2026-12-31")}
RTH0, RTH1 = (9 * 60 + 30 + 6 * 60), (16 * 60 + 6 * 60)  # 09:30 / 16:00 in globex minutes (18:00 = 0)

FOMC_2016 = """2016-07-27 2016-09-21 2016-11-02 2016-12-14 2017-02-01 2017-03-15 2017-05-03 2017-06-14
2017-07-26 2017-09-20 2017-11-01 2017-12-13 2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01
2018-09-26 2018-11-08 2018-12-19 2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18
2019-10-30 2019-12-11 2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15 2022-01-26
2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14 2023-02-01 2023-03-22
2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13 2024-01-31 2024-03-20 2024-05-01
2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18 2025-01-29 2025-03-19 2025-05-07 2025-06-18
2025-07-30 2025-09-17 2025-10-29 2025-12-10 2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29
2026-09-16""".split()


def period_of(dates) -> np.ndarray:
    d = pd.DatetimeIndex(dates)
    out = np.full(len(d), "", dtype=object)
    for k, (a, b) in PERIODS.items():
        out[(d >= a) & (d <= b)] = k
    return out


def lunar_phase(dates) -> np.ndarray:
    """Moon age in days (0 = new moon), from the mean synodic month."""
    ref = pd.Timestamp("2000-01-06 18:14")
    days = (pd.DatetimeIndex(dates) - ref).total_seconds() / 86400
    return np.mod(days, 29.530588853)


class Data:
    pass


def build():
    df = pd.read_parquet(SRC)
    ts = df.ts
    # globex day: 18:00 ET belongs to the next weekday
    d = ts.dt.normalize()
    g = d.where(ts.dt.hour < 18, d + pd.Timedelta(days=1))
    wd = g.dt.dayofweek
    g = g.where(wd != 5, g + pd.Timedelta(days=2)).where(wd != 6, g + pd.Timedelta(days=1))
    gm = ((ts - (g - pd.Timedelta(hours=6))).dt.total_seconds() // 60).astype(int)  # minutes since 18:00 prev day
    keep = (gm >= 0) & (gm < 23 * 60)
    df, g, gm = df[keep], g[keep], gm[keep]
    # 5-minute key
    gnum = ((g - pd.Timestamp("2000-01-01")).dt.days).to_numpy()
    k5 = gnum * 1000 + (gm.to_numpy() // 5)
    brk = np.r_[0, np.where(np.diff(k5) != 0)[0] + 1]
    o1, h1, l1, c1 = (df[c].to_numpy(float) for c in ("Open", "High", "Low", "Close"))
    v1 = df.Volume.to_numpy(float)
    dl1 = (df.Ask - df.Bid).to_numpy(float)
    tp1 = (h1 + l1 + c1) / 3
    D = Data()
    D.o = o1[brk]; D.h = np.maximum.reduceat(h1, brk); D.l = np.minimum.reduceat(l1, brk)
    D.c = c1[np.r_[brk[1:], len(c1)] - 1]
    D.v = np.add.reduceat(v1, brk); D.dl = np.add.reduceat(dl1, brk)
    D.pv = np.add.reduceat(tp1 * v1, brk); D.p2v = np.add.reduceat(tp1 * tp1 * v1, brk)
    D.gday = g.to_numpy()[brk]
    D.gmin = (gm.to_numpy()[brk] // 5) * 5
    D.ts = ts.to_numpy()[brk]
    n = len(D.o)
    D.rth = (D.gmin >= RTH0) & (D.gmin < RTH1)
    # day index of each bar
    days, D.di = np.unique(D.gday, return_inverse=True)
    D.days = pd.DatetimeIndex(days)
    # anchored VWAPs (cumulative within anchor groups)
    def anchored(groups, mask=None):
        vv = D.v if mask is None else np.where(mask, D.v, 0.0)
        pv = D.pv if mask is None else np.where(mask, D.pv, 0.0)
        p2 = D.p2v if mask is None else np.where(mask, D.p2v, 0.0)
        s = pd.DataFrame({"g": groups, "v": vv, "pv": pv, "p2": p2}).groupby("g").cumsum()
        with np.errstate(invalid="ignore", divide="ignore"):
            vw = s.pv.to_numpy() / s.v.to_numpy()
            sd = np.sqrt(np.maximum(s.p2.to_numpy() / s.v.to_numpy() - vw ** 2, 0))
        return vw, sd
    gd = pd.DatetimeIndex(D.gday)
    D.vw_g, D.sd_g = anchored(D.di)                       # globex day from 18:00
    D.vw_r, D.sd_r = anchored(D.di, D.rth)                # RTH VWAP (valid inside RTH)
    wk = (gd - pd.to_timedelta(gd.dayofweek, unit="D")).to_numpy()
    D.vw_w, D.sd_w = anchored(wk)
    mo = (gd.year * 12 + gd.month).to_numpy()
    D.vw_m, D.sd_m = anchored(mo)
    D.cvd_day = pd.Series(D.dl).groupby(D.di).cumsum().to_numpy()
    D.cvd = np.cumsum(D.dl)
    D.flow_ok = D.gday >= np.datetime64("2010-06-01")     # bid/ask volume reliable from mid 2010
    D.period = period_of(D.gday)
    _daily(D)
    return D


def _daily(D):
    nd = len(D.days)
    di = D.di
    first = np.r_[0, np.where(np.diff(di) != 0)[0] + 1]
    last = np.r_[first[1:], len(di)]
    rows = []
    for k in range(nd):
        s, e = first[k], last[k]
        r = D.rth[s:e]
        on = ~r & (D.gmin[s:e] < RTH0)
        ri = np.where(r)[0] + s
        oi = np.where(on)[0] + s
        if len(ri) < 40:
            rows.append([np.nan] * 16)
            continue
        rows.append([D.o[ri[0]], D.h[ri].max(), D.l[ri].min(), D.c[ri[-1]],
                     D.o[s], D.h[s:e].max(), D.l[s:e].min(), D.c[e - 1],
                     D.h[oi].max() if len(oi) else np.nan, D.l[oi].min() if len(oi) else np.nan,
                     D.v[ri].sum(), D.dl[ri].sum(), D.v[s:e].sum(), D.dl[s:e].sum(), ri[0], ri[-1]])
    T = pd.DataFrame(rows, index=D.days, columns=["O", "H", "L", "C", "gO", "gH", "gL", "gC", "onH", "onL",
                                                  "vol", "delta", "gvol", "gdelta", "i_open", "i_close"])
    T["ok"] = T.C.notna()
    T = T[T.ok].copy()
    T["pC"] = T.C.shift()
    T["ret"] = T.C / T.pC - 1
    tr = np.maximum(T.H - T.L, np.maximum((T.H - T.pC).abs(), (T.L - T.pC).abs()))
    T["atr"] = tr.rolling(20).mean().shift()
    T["ma200"] = T.C.rolling(200).mean().shift()
    T["bull"] = T.pC > T.ma200
    idx = T.index
    T["wd"] = idx.dayofweek
    T["dom"] = idx.day
    ym = idx.year * 12 + idx.month
    T["tdm"] = pd.Series(1, index=idx).groupby(ym).cumsum().to_numpy()          # trading day of month
    T["tdm_rev"] = pd.Series(1, index=idx)[::-1].groupby(ym[::-1]).cumsum()[::-1].to_numpy()  # 1 = last
    T["month"] = idx.month
    T["woy"] = idx.isocalendar().week.to_numpy()
    third_fri = set()
    for y in range(idx[0].year, idx[-1].year + 1):
        for mth in range(1, 13):
            x = pd.Timestamp(y, mth, 15)
            third_fri.add(x + pd.Timedelta(days=(4 - x.dayofweek) % 7))
    T["opex"] = [x in third_fri for x in idx]
    T["opex_week"] = [(x + pd.Timedelta(days=(4 - x.dayofweek) % 7)) in third_fri for x in idx]
    T["quad"] = T.opex & idx.month.isin([3, 6, 9, 12])
    allbd = pd.bdate_range(idx[0], idx[-1])
    hol = allbd.difference(idx)
    T["pre_hol"] = [((x + pd.offsets.BDay(1)) in hol) for x in idx]
    T["post_hol"] = [((x - pd.offsets.BDay(1)) in hol) for x in idx]
    fomc = set(pd.to_datetime(FOMC_2016))
    T["fomc"] = [x in fomc for x in idx]
    T["moon"] = lunar_phase(idx + pd.Timedelta(hours=12))
    T["period"] = period_of(idx)
    D.T = T
    D.dpos = pd.Series(np.arange(len(D.days)), index=D.days)


def load():
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, "rb"))
    D = build()
    pickle.dump(D, open(CACHE, "wb"), protocol=4)
    return D


if __name__ == "__main__":
    import time
    import data as _self  # build through the module so the pickle refers to data.Data
    t = time.time()
    D = _self.load()
    print(len(D.o), "5m bars", len(D.T), "days", f"{time.time() - t:.0f}s")
    print(D.T.tail(3).T)
