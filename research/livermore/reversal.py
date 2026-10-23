"""Livermore one-day reversal on ES daily bars (RTH), 2009-2026.

Signals (decided at the close of day t, trade at the next open):
  BULL   close > previous close, low < previous low, volume > previous volume          -> long
  BEAR_A close < previous close, low > previous low, volume > previous volume          -> short (as given)
  BEAR_K close < previous close, high > previous high, volume > previous volume        -> short (classic key reversal)
Variants: without the volume condition; "after a move" (bull: the low is a 20-day low, bear: the high is a 20-day high).
Outcome: return from the next open to the close after h = 1, 2, 3, 5, 10 days, in ATR, minus cost; excess = minus the
average return of all days in the same year for the same side (removes the ES drift). Non-overlapping signals only.
Periods: 2009-17, 2018-21, 2022-26. Also a simple system (hold 5 days, stop 1 ATR) vs buy & hold.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
OUT = os.path.join(HERE, "out")
H = (1, 2, 3, 5, 10)


def main():
    import features as F
    T = F.load()["T"][["O", "H", "L", "C", "ATR", "vol"]].copy()
    T["ATRp"] = T.ATR.shift()
    T = T.loc["2008-09":]
    C, Hh, L, V = T.C, T.H, T.L, T.vol
    up, dn = C > C.shift(), C < C.shift()
    vol_up = V > V.shift()
    sig = {
        "BULL (zadání)": (up & (L < L.shift()) & vol_up, 1),
        "BULL bez objemu": (up & (L < L.shift()), 1),
        "BULL po poklesu (low = 20denní low)": (up & (L < L.shift()) & vol_up & (L <= L.rolling(20).min()), 1),
        "BEAR_A (zadání: low > předchozí low)": (dn & (L > L.shift()) & vol_up, -1),
        "BEAR_K (klasický key reversal: high > předchozí high)": (dn & (Hh > Hh.shift()) & vol_up, -1),
        "BEAR_K bez objemu": (dn & (Hh > Hh.shift()), -1),
        "BEAR_K po růstu (high = 20denní high)": (dn & (Hh > Hh.shift()) & vol_up & (Hh >= Hh.rolling(20).max()), -1),
    }
    o = T.O.to_numpy(); c = T.C.to_numpy(); a = T.ATRp.to_numpy(); n = len(T)
    yrs = T.index.year.to_numpy()
    per = np.where(yrs <= 2017, "2009–17", np.where(yrs <= 2021, "2018–21", "2022–26"))
    rows = []
    for h in H:
        fwd = np.full(n, np.nan)
        fwd[:-h] = (c[h:] - o[1:n - h + 1]) / a[:-h]          # entry next open (t+1), exit close t+h
        cost = 0.5 / a
        for side in (1, -1):
            base = pd.Series(side * fwd, index=T.index).groupby(yrs).transform("mean").to_numpy()
            for name, (s, sd) in sig.items():
                if sd != side:
                    continue
                idx = np.flatnonzero(s.fillna(False).to_numpy() & np.isfinite(fwd) & np.isfinite(a) & (yrs >= 2009))
                keep, last = [], -10**9
                for i in idx:
                    if i - last >= h:
                        keep.append(i); last = i
                keep = np.array(keep)
                r = side * fwd[keep] - cost[keep]
                ex = side * fwd[keep] - base[keep]
                row = dict(signal=name, h=h, n=len(keep), R=r.mean(), t_R=r.mean() / r.std() * np.sqrt(len(r)),
                           excess=ex.mean(), t_excess=ex.mean() / ex.std() * np.sqrt(len(ex)), win=(r > 0).mean())
                for p in ("2009–17", "2018–21", "2022–26"):
                    m = per[keep] == p
                    row[f"excess {p}"] = ex[m].mean(); row[f"n {p}"] = int(m.sum())
                rows.append(row)
    S = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
    print(S.round(3).to_string())
    S.round(4).to_csv(os.path.join(OUT, "reversal_events.csv"), index=False)
    # simple system: BULL (zadání) long, hold 5 days, stop 1 ATR; one position at a time; daily % P&L vs B&H
    s = sig["BULL (zadání)"][0].fillna(False).to_numpy()
    pos = np.zeros(n); i = 0
    lo = T.L.to_numpy()
    tr = []
    while i < n - 1:
        if s[i] and np.isfinite(a[i]) and yrs[i] >= 2009:
            e = o[i + 1]; stp = e - a[i]; j = i + 1; out = None
            while j < n and j <= i + 5:
                pos[j] = 1
                if lo[j] <= stp:
                    out = stp; break
                j += 1
            j = min(j, n - 1)
            px = out if out is not None else c[j]
            tr.append((T.index[i + 1], (px - e - 0.5) / e))
            i = j + 1
        else:
            i += 1
    TR = pd.DataFrame(tr, columns=["d", "r"]).set_index("d")
    sysr = TR.r.groupby(TR.index.year).apply(lambda x: (1 + x).prod() - 1)
    bh = T.C.groupby(T.index.year).last().pct_change()
    Y = pd.DataFrame({"systém %": sysr * 100, "B&H %": bh * 100, "obchodů": TR.r.groupby(TR.index.year).size(),
                      "win %": TR.r.groupby(TR.index.year).apply(lambda x: (x > 0).mean() * 100)}).loc[2009:].round(1)
    print(Y.to_string())
    tot = (1 + TR.r).prod() ** (1 / 17.7) - 1
    print("systém CAGR", round(tot * 100, 2), "% , v trhu", round(pos.mean() * 100, 1), "% dní, obchodů", len(TR),
          ", průměr na obchod", round(TR.r.mean() * 100, 3), "%, t", round(TR.r.mean() / TR.r.std() * np.sqrt(len(TR)), 2))
    Y.to_csv(os.path.join(OUT, "reversal_system_years.csv"))


if __name__ == "__main__":
    main()
