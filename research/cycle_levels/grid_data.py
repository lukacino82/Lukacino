"""Cycle-level grid read off the user's US500Cash weekly chart, and ES 1-min data converted to cash-index equivalent.

Grid (axis labels of the chart): red cycle levels are geometric, R_k = 2908.44 * r^k with r = (7801.36 / 2908.44)^(1/3)
= 1.38944 (2093.2, 2908.44, 4041.09, 5614.79, 7801.36, 10839.6 ...). Each red-to-red cycle is split linearly into
quarters: purple 1/4, white/yellow 1/2, blue 3/4 (e.g. 5614.79 / 6161.45 / 6708.08 / 7254.7 / 7801.36).
Grid coordinate g(p) = k + (p - R_k) / (R_{k+1} - R_k): integer = red level, x.25 / x.5 / x.75 = the dashed levels.
Null grids: the same construction with R0 = 2908.44 * r^u, u ~ U(0, 1) (random phase).

Data: raw (not back-adjusted) ES front month 1-min 2018-07 .. 2026-09 (ES3000). The chart is a cash CFD, so futures are
converted to cash with fair value: S = F / (1 + (rate - div) * T), T = days to expiry of the held contract / 365,
rate = yearly average effective fed funds, div = S&P dividend yield. Rolls on the Thursday 8 days before expiry.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

R0 = 2908.44
RATIO = (7801.36 / 2908.44) ** (1 / 3)
RATE = {2018: 1.83, 2019: 2.16, 2020: 0.38, 2021: 0.08, 2022: 1.68, 2023: 5.02, 2024: 5.14, 2025: 4.2, 2026: 3.7}
DIV = {2018: 1.9, 2019: 1.9, 2020: 1.8, 2021: 1.4, 2022: 1.6, 2023: 1.5, 2024: 1.3, 2025: 1.25, 2026: 1.2}
CACHE = "/tmp/claude-0/data/es1m_cash.npz"


def coord(p, r0=R0, ratio=RATIO):
    lr = np.log(ratio)
    k = np.floor(np.log(p / r0) / lr)
    lo = r0 * ratio ** k
    return k + (p - lo) / (lo * (ratio - 1))


def level_price(g, r0=R0, ratio=RATIO):
    k = np.floor(g)
    lo = r0 * ratio ** k
    return lo + (g - k) * lo * (ratio - 1)


def _expiry(y, m):
    d = pd.Timestamp(y, m, 1)
    return d + pd.Timedelta(days=(4 - d.weekday()) % 7 + 14)          # third Friday


def load():
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {k: z[k] for k in z.files}
    D = pd.read_parquet("/tmp/claude-0/data/es1m.parquet")
    ts = pd.to_datetime(D.ts)
    day = pd.DatetimeIndex(ts.dt.normalize().unique())
    exps = [_expiry(y, m) for y in range(2018, 2028) for m in (3, 6, 9, 12)]
    rolls = [e - pd.Timedelta(days=8) for e in exps]
    held = np.searchsorted(np.array(rolls, "datetime64[ns]"), day.values, side="right")   # index of held contract
    T = (np.array(exps, "datetime64[ns]")[held] - day.values) / np.timedelta64(1, "D") / 365
    yrs = pd.DatetimeIndex(day).year
    carry = np.array([(RATE[y] - DIV[y]) / 100 for y in yrs])
    f = pd.Series(1 + carry * T, index=day)
    fac = f.reindex(ts.dt.normalize()).to_numpy()
    out = dict(ts=ts.values, H=D.High.to_numpy() / fac, L=D.Low.to_numpy() / fac, C=D.Close.to_numpy() / fac,
               O=D.Open.to_numpy() / fac, basis=(D.Close.to_numpy() * (1 - 1 / fac)))
    np.savez(CACHE, **out)
    return out


if __name__ == "__main__":
    d = load()
    s = pd.DataFrame({k: d[k] for k in ("H", "L", "C", "basis")}, index=pd.DatetimeIndex(d["ts"]))
    print("levels:", [round(float(level_price(x)), 2) for x in np.arange(-1, 3.01, 0.25)])
    print("basis pts by year:", s.basis.groupby(s.index.year).mean().round(1).to_dict())
    for a, b, name, ref in (("2020-03-20", "2020-03-25", "covid low", 2191.86), ("2022-10-12", "2022-10-14", "2022 low", 3491.58),
                            ("2022-01-03", "2022-01-05", "2022 high", 4818.62), ("2025-04-06", "2025-04-08", "2025 low", 4835.04)):
        x = s.loc[a:b]
        v = x.L.min() if "low" in name else x.H.max()
        print(f"{name}: ES->cash {v:.1f} vs S&P cash {ref} ({v - ref:+.1f})")
