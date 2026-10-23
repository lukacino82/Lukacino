"""US500Cash-equivalent 1-min prices 2008-05 .. 2026-09 for testing the BCL cycle lines.

2018-07 .. 2026-09: raw ES front month (ES3000) mapped on the broker's own US500Cash price: for every broker day
(server time = New York + 7 h) offset = ES close at 16:59 ET - broker D1 close; cash(t) = ES(t) - offset(day).
Checked against broker H1 closes: median error 0.75 point.
2008-05 .. 2018-07: back-adjusted ES2008 (additive, rolls on the Sunday 5 days before expiry). Raw futures are
rebuilt by adding back the roll gaps, modelled as gap = F x (rate - dividend yield) x 0.25 (3M LIBOR, S&P dividend
yield), then converted to cash with fair value and corrected to known S&P 500 closes (linear interpolation of the
residual between anchor dates). Precision of this part is a few points, enough for the weekly lines and the red daily
lines, not for the daily quarter lines (see VYSLEDKY.md).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

DATA = "/tmp/claude-0/data"
CACHE = os.path.join(DATA, "bcl_cash.parquet")
LIBOR = {2008: 2.9, 2009: 0.7, 2010: 0.35, 2011: 0.35, 2012: 0.43, 2013: 0.27, 2014: 0.23, 2015: 0.32, 2016: 0.74,
         2017: 1.26, 2018: 2.3}
DIVY = {2008: 2.6, 2009: 2.4, 2010: 1.9, 2011: 2.0, 2012: 2.1, 2013: 2.0, 2014: 1.9, 2015: 2.1, 2016: 2.1, 2017: 1.9,
        2018: 1.9}
SPX = {"2008-12-31": 903.25, "2009-03-09": 676.53, "2009-12-31": 1115.10, "2010-07-02": 1022.58,
       "2010-12-31": 1257.64, "2011-10-03": 1099.23, "2011-12-30": 1257.60, "2012-12-31": 1426.19,
       "2013-12-31": 1848.36, "2014-12-31": 2058.90, "2015-08-25": 1867.61, "2015-12-31": 2043.94,
       "2016-02-11": 1829.08, "2016-12-30": 2238.83, "2017-12-29": 2673.61, "2018-01-26": 2872.87,
       "2018-02-08": 2581.00}
SWITCH = pd.Timestamp("2018-07-08 18:00")


def _third_friday(y, m):
    d = pd.Timestamp(y, m, 1)
    return d + pd.Timedelta(days=(4 - d.weekday()) % 7 + 14)


def _carry(ts):
    y = ts.year.to_numpy() if hasattr(ts, "year") else np.array([t.year for t in ts])
    return np.array([(LIBOR.get(v, 2.3) - DIVY.get(v, 1.9)) / 100 for v in y])


def broker_daily():
    B = pd.read_csv(os.path.join(DATA, "us500", "US500Cash1440.csv"), header=None, names=["d", "t", "O", "H", "L", "C", "V"])
    B.index = pd.to_datetime(B.d, format="%Y.%m.%d")
    return B[["O", "H", "L", "C"]]


def recent():
    E = pd.read_parquet(os.path.join(DATA, "es1m.parquet"), columns=["ts", "Open", "High", "Low", "Close"])
    E["ts"] = pd.to_datetime(E.ts)
    E["bday"] = (E.ts + pd.Timedelta(hours=7)).dt.normalize()
    last = E[E.ts.dt.hour < 17].groupby(E.ts.dt.normalize()).Close.last()
    off = (last - broker_daily().C).dropna()
    o = off.reindex(E.bday).ffill().bfill().to_numpy()
    out = pd.DataFrame({"ts": E.ts, "O": E.Open - o, "H": E.High - o, "L": E.Low - o, "C": E.Close - o})
    return out


def early():
    A = pd.read_parquet(os.path.join(DATA, "es2008.parquet"), columns=["ts", "Open", "High", "Low", "Close"])
    A["ts"] = pd.to_datetime(A.ts)
    A = A[A.ts < SWITCH].reset_index(drop=True)
    exps = [_third_friday(y, m) for y in range(2008, 2019) for m in (3, 6, 9, 12)]
    rolls = [e - pd.Timedelta(days=5) + pd.Timedelta(hours=18) for e in exps]
    rolls = [r for r in rolls if A.ts.iloc[0] < r < SWITCH]
    off_after = 831.0                                   # offset (adjusted - raw) right after 2018-07-08
    offs = []                                           # offset valid before each roll, newest first
    for r in reversed(rolls):
        i = A.ts.searchsorted(r)
        f = A.Close.iloc[i] - off_after                 # raw front (new) contract price at the roll
        y = r.year
        gap = f * (LIBOR[y] - DIVY[y]) / 100 * 0.25
        off_after = off_after + gap
        offs.append((r, off_after))
    edges = [A.ts.iloc[0]] + rolls + [SWITCH]
    offv = np.zeros(len(A))
    seq = [o for _, o in reversed(offs)] + [831.0]      # offset for each interval between edges
    idx = A.ts.searchsorted(pd.DatetimeIndex(edges))
    for k in range(len(edges) - 1):
        offv[idx[k]:idx[k + 1]] = seq[k]
    raw = {c: A[c].to_numpy() - offv for c in ("Open", "High", "Low", "Close")}
    # fair value -> cash
    held = np.searchsorted(np.array(rolls, "datetime64[ns]"), A.ts.values, side="right")
    exp_arr = np.array([e for e in exps if e - pd.Timedelta(days=5) > A.ts.iloc[0] - pd.Timedelta(days=95)][:len(rolls) + 1],
                       "datetime64[ns]")
    T = np.clip((exp_arr[np.minimum(held, len(exp_arr) - 1)] - A.ts.values) / np.timedelta64(1, "D") / 365, 0, 0.3)
    fac = 1 + _carry(A.ts.dt) * T
    out = pd.DataFrame({"ts": A.ts, **{k[0]: v / fac for k, v in raw.items()}})
    # anchor correction at 16:00 ET closes
    res = []
    for d, v in SPX.items():
        t = pd.Timestamp(d + " 15:59")
        j = out.ts.searchsorted(t, side="right") - 1
        res.append((out.ts.iloc[j], v - out.C.iloc[j]))
    R = pd.Series(dict(res)).sort_index()
    corr = np.interp(out.ts.values.astype("int64"), R.index.values.astype("int64"), R.to_numpy())
    for c in "OHLC":
        out[c] = out[c] + corr
    return out, R


def load():
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    e, _ = early()
    df = pd.concat([e, recent()], ignore_index=True).sort_values("ts").reset_index(drop=True)
    df.to_parquet(CACHE)
    return df


if __name__ == "__main__":
    e, R = early()
    print("residuals at S&P anchors before correction (points):"); print(R.round(2).to_string())
    df = load()
    print(df.head(2)); print(df.tail(2)); print(len(df))
