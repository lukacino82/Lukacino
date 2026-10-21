"""Mechanisms from the literature tested on ES2008 (pre-specified rules, one test each).

a) Overnight reversal after an RTH sell-off (dealer inventory, Boyarchenko-Larsen-Whelan) and the 02:00-03:00 ET
   overnight-drift window, before / after 2021.
b) Market intraday momentum (Gao-Han-Li-Zhou): return prior RTH close -> 10:00 predicts 15:30 -> 16:00.
c) Dash for cash / turn of month (Etula et al.): average return by trading day relative to month end.
d) Rebalancing proxy (Harvey-Mazzoleni-Melone): last 4 trading days of the month after a strong / weak month-to-date.
e) Volatility-control buy-back: after a high-vol episode (10D realised vol >= 25 %) once vol falls 20 % from its
   peak, long 20 days.
f) False recoveries: every +5 % rally off a low while ES is >= 10 % below its high - did it make a new low later?

Prices are back-adjusted ES (1-minute, ET). Costs 0.5 point per round trip. Periods: 2008-2015, 2016-2020, 2021-2026.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
import features as F  # noqa: E402

OUT = os.path.join(HERE, "out")
COST = 0.5
CACHE = "/tmp/claude-0/data/mech_snap.pkl"
# minutes since 18:00 of the previous calendar day
SNAP = {"18:00": 0, "02:00": 480, "03:00": 540, "09:30": 930, "10:00": 960, "15:30": 1290, "16:00": 1320}


def per(idx):
    y = pd.DatetimeIndex(idx).year
    return np.where(y <= 2015, "2008–15", np.where(y <= 2020, "2016–20", "2021–26"))


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x)) if len(x) > 5 and x.std() > 0 else np.nan


def summ(x, idx, name):
    x = pd.Series(np.asarray(x, float), index=idx).dropna()
    rows = [dict(test=name, period="vše", n=len(x), mean=x.mean(), t=tstat(x), win=(x > 0).mean())]
    for p in ("2008–15", "2016–20", "2021–26"):
        s = x[per(x.index) == p]
        rows.append(dict(test=name, period=p, n=len(s), mean=s.mean(), t=tstat(s), win=(s > 0).mean()))
    return rows


def snapshots():
    """price (close of the last bar strictly before each snapshot minute) for every globex day"""
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    df, g, gm = F.load_1m()
    d = pd.DataFrame({"g": g.values, "gm": gm.values, "c": df.Close.values, "o": df.Open.values})
    out = {}
    for k, m in SNAP.items():
        if m == 0:
            first = d.groupby("g").first()
            out["open_globex"] = first.o
            continue
        s = d[d.gm < m].groupby("g").last()
        s = s[s.gm >= m - 30]                     # require a bar within 30 min before the snapshot
        out[k] = s.c
    S = pd.DataFrame(out)
    S.to_pickle(CACHE)
    return S


def main():
    os.makedirs(OUT, exist_ok=True)
    T = F.load()["T"]
    S = snapshots().reindex(T.index)
    rows = []
    # ---------- a) overnight reversal and the 02-03 window
    on = (T.O.shift(-1) - T.C)                     # RTH close -> next RTH open, points
    rth = (T.C - T.O) / T.ATR                      # today's RTH move in ATR
    sell = rth <= rth.rolling(250, min_periods=100).quantile(0.2).shift()
    rally = rth >= rth.rolling(250, min_periods=100).quantile(0.8).shift()
    a_all = on - COST
    rows += summ(a_all, T.index, "a) noční držení každý den (body)")
    rows += summ(a_all[sell], T.index[sell], "a) noční držení po RTH výprodeji (dolní kvintil)")
    rows += summ(a_all[rally], T.index[rally], "a) noční držení po RTH rally (horní kvintil)")
    w = (S["03:00"] - S["02:00"])                  # gross, the window itself
    rows += summ(w, S.index, "a) okno 02:00–03:00 ET (body, hrubě)")
    rows += summ(w[sell.shift().fillna(False).astype(bool).reindex(S.index, fill_value=False)],
                 S.index[sell.shift().fillna(False).astype(bool).reindex(S.index, fill_value=False)], "a) okno 02–03 po předchozím RTH výprodeji")
    # ---------- b) intraday momentum
    r1 = (S["10:00"] - T.C.shift()) / T.ATR.shift()
    last = S["16:00"] - S["15:30"]
    sig = np.sign(r1)
    b_pts = sig * last - COST
    rows += summ(b_pts, T.index, "b) intradenní momentum: znaménko (close→10:00) na 15:30–16:00")
    hv = (T.rv_rank.shift() > 0.8)
    rows += summ(b_pts[hv], T.index[hv], "b) totéž jen ve dnech vysoké vol (horní kvintil)")
    big = r1.abs() > r1.abs().rolling(250, min_periods=100).quantile(0.8).shift()
    rows += summ(b_pts[big], T.index[big], "b) totéž jen při velkém ranním pohybu (horní kvintil |r1|)")
    rows += summ(sig[hv] * last[hv], T.index[hv], "b) vysoká vol, hrubě bez nákladů")
    rows += summ(sig * last, T.index, "b) všechny dny, hrubě bez nákladů")
    # ---------- c) return by trading day relative to month end
    ret = T.C.pct_change() * 100
    m = T.index.to_period("M")
    pos_end = T.groupby(m).cumcount(ascending=False)             # 0 = last trading day
    pos_start = T.groupby(m).cumcount()                           # 0 = first trading day
    prof = []
    for k in range(7, -1, -1):
        s = ret[pos_end == k]
        prof.append(dict(day=f"T-{k}" if k else "T (poslední den)", n=len(s), mean_pct=s.mean(), t=tstat(s)))
    for k in range(0, 4):
        s = ret[pos_start == k]
        prof.append(dict(day=f"+{k + 1}. den nového měsíce", n=len(s), mean_pct=s.mean(), t=tstat(s)))
    allm = dict(day="průměrný den", n=ret.notna().sum(), mean_pct=ret.mean(), t=tstat(ret))
    prof.append(allm)
    P = pd.DataFrame(prof)
    # pre-specified TOM trade: long from close of T-1 to close of the 3rd day of the next month
    tom_mask = (pos_end == 0) | (pos_start <= 2)
    tom = ret.where(tom_mask)
    rows += summ(tom.dropna(), tom.dropna().index, "c) turn of month: dny T, +1, +2, +3 (% denně)")
    pre = ret.where((pos_end >= 3) & (pos_end <= 5))
    rows += summ(pre.dropna(), pre.dropna().index, "c) T-5 až T-3 (tlak před výplatami, % denně)")
    # ---------- d) rebalancing proxy
    mtd = T.C / T.groupby(m).C.transform("first") - 1             # month-to-date at each close (approx from 1st close)
    d_rows = []
    for mo, g in T.groupby(m):
        if len(g) < 12:
            continue
        i5 = g.index[-5]                                           # close of the 5th-last trading day
        m5 = g.C.loc[i5] / T.C.shift().loc[g.index[0]] - 1          # month return up to that close
        fwd = (g.C.iloc[-1] - g.C.loc[i5]) / g.C.loc[i5] * 100      # last 4 trading days
        d_rows.append(dict(month=str(mo), mtd=m5, fwd=fwd, q=mo.month in (3, 6, 9, 12)))
    D = pd.DataFrame(d_rows).dropna()
    D["tercile"] = pd.qcut(D.mtd, 3, labels=["slabý měsíc", "střední", "silný měsíc"])
    D.index = pd.to_datetime(D.month)
    for lab in ["slabý měsíc", "střední", "silný měsíc"]:
        s = D[D.tercile == lab]
        rows += summ(s.fwd, s.index, f"d) poslední 4 dny měsíce po: {lab} (%)")
        s = D[(D.tercile == lab) & D.q]
        rows += summ(s.fwd, s.index, f"d) totéž jen konec kvartálu: {lab} (%)")
    # ---------- e) vol-control buy-back
    rv10 = T.ret.rolling(10).std() * np.sqrt(252)
    peak = rv10.rolling(20).max()
    cond = (peak >= 0.25) & (rv10 <= 0.8 * peak)
    first = cond & ~cond.shift().fillna(False).astype(bool)
    # one signal per episode: no new signal within 40 days
    sig_e = np.zeros(len(T), bool); last_i = -999
    for i, v in enumerate(first.to_numpy()):
        if v and i - last_i > 40:
            sig_e[i] = True; last_i = i
    fwd20 = (T.C.shift(-20) - T.nO) / T.ATR                         # entry next open, 20 days, ATR units
    base20 = fwd20.groupby(T.index.year).transform("mean")
    e_idx = T.index[sig_e]
    rows += summ((fwd20 - COST / T.ATR)[sig_e], e_idx, "e) po vrcholu vol (≥25 %) a poklesu o 20 %: long 20 dní (ATR)")
    rows += summ((fwd20 - base20)[sig_e], e_idx, "e) totéž: nadvýnos proti průměrnému dni roku (ATR)")
    E = pd.DataFrame({"date": e_idx, "peak_vol": peak[sig_e].values, "fwd20_atr": fwd20[sig_e].values,
                      "fwd20_pct": ((T.C.shift(-20) - T.nO) / T.nO * 100)[sig_e].values})
    # ---------- f) false recoveries
    hi = T.gC.rolling(252, min_periods=1).max(); px = T.gC
    f_rows = []; i = 0; n = len(T)
    arr = px.to_numpy(); hia = hi.to_numpy(); idx = T.index
    low_i = None
    while i < n:
        dd = arr[i] / hia[i] - 1
        if dd <= -0.10:
            # track low since drawdown started
            if low_i is None or arr[i] < arr[low_i]:
                low_i = i
            if arr[i] >= arr[low_i] * 1.05:
                # recovery candidate: did price make a new low below arr[low_i] in the next 60 days before regaining the old high?
                j_end = min(n, i + 120)
                fut = arr[i + 1:j_end]
                new_low = (fut < arr[low_i]).any()
                ret20 = arr[min(n - 1, i + 20)] / arr[i] - 1
                ret60 = arr[min(n - 1, i + 60)] / arr[i] - 1
                f_rows.append(dict(date=idx[i].date(), dd_at_low=arr[low_i] / hia[low_i] - 1, days_from_low=i - low_i,
                                   rv20=T.rv20.iloc[i], above_ma200=bool(arr[i] > T.ma200.iloc[i]) if np.isfinite(T.ma200.iloc[i]) else None,
                                   ma200_slope=(T.ma200.iloc[i] / T.ma200.iloc[i - 20] - 1) if i >= 20 else np.nan,
                                   false_recovery=bool(new_low), ret20=ret20, ret60=ret60))
                low_i = None
                # skip ahead until price falls 5 % below this point or regains the high (one candidate per swing)
                k = i + 1
                while k < n and k - i < 60 and arr[k] > arr[i] * 0.95 and arr[k] < hia[k]:
                    k += 1
                i = k
                continue
        else:
            low_i = None
        i += 1
    FR = pd.DataFrame(f_rows)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "tests.csv"), index=False)
    P.to_csv(os.path.join(OUT, "month_profile.csv"), index=False)
    D.to_csv(os.path.join(OUT, "rebalancing.csv"))
    E.to_csv(os.path.join(OUT, "vol_buyback.csv"), index=False)
    FR.to_csv(os.path.join(OUT, "false_recoveries.csv"), index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 70)
    print(R.round(3).to_string()); print(P.round(3).to_string()); print(E.round(2).to_string()); print(FR.round(3).to_string())
    if len(FR):
        print(FR.groupby("false_recovery")[["dd_at_low", "days_from_low", "rv20", "ma200_slope", "ret20", "ret60"]].mean().round(3))


if __name__ == "__main__":
    main()


def false_recoveries_atr(T, dd_atr=8.0, rally_atr=4.0, horizon=120):
    """scale-free version of f): back-adjusted prices understate early % drawdowns, so measure in ATR units"""
    px = T.gC.to_numpy(); hi = T.gC.rolling(252, min_periods=1).max().to_numpy(); atr = T.ATR.to_numpy()
    idx = T.index; n = len(T); rows = []; i = 0; low_i = None
    while i < n:
        if np.isfinite(atr[i]) and (hi[i] - px[i]) >= dd_atr * atr[i]:
            if low_i is None or px[i] < px[low_i]:
                low_i = i
            if px[i] - px[low_i] >= rally_atr * atr[low_i]:
                fut = px[i + 1:min(n, i + horizon)]
                rows.append(dict(date=idx[i].date(), dd_atr=(hi[low_i] - px[low_i]) / atr[low_i], dd_pct=px[low_i] / hi[low_i] - 1,
                                 days_from_low=i - low_i, rally_days_per_atr=(i - low_i) / rally_atr, rv20=T.rv20.iloc[i],
                                 false_recovery=bool((fut < px[low_i]).any()),
                                 ret20=px[min(n - 1, i + 20)] / px[i] - 1, ret60=px[min(n - 1, i + 60)] / px[i] - 1))
                low_i = None
                k = i + 1
                while k < n and k - i < 60 and px[k] > px[i] - 3 * atr[i] and px[k] < hi[k]:
                    k += 1
                i = k
                continue
        else:
            low_i = None
        i += 1
    return pd.DataFrame(rows)

