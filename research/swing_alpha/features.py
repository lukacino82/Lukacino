"""SWING ALPHA P0/P1: data audit and the daily feature store (ES2008, 1-minute, back-adjusted, ET).

Every feature of day t is computed from data up to the RTH close of day t (available_at = 16:00 ET
of t); trades enter at the RTH open of day t+1.

Market Profile: ES2008 has no Volume-at-Price, so the RTH profile is reconstructed from 1-minute
bars by spreading each bar's volume evenly over the 0.25 price ticks between its low and high.
POC = tick with most volume (ties -> closest to the profile midpoint). Value area = expand from
the POC one tick at a time towards the side with more volume (tie -> up) until 70 % of volume.
VWAP: daily = RTH session, weekly / monthly = all globex bars from the first session of the week
or month (typical price x volume).
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd
from numba import njit

SRC = "/tmp/claude-0/data/es2008.parquet"
CACHE = "/tmp/claude-0/data/sa_daily.pkl"
TICK = 0.25
RTH0, RTH1 = 930, 1320  # minutes since 18:00 of the previous day


@njit(cache=True)
def profile(lo_b, hi_b, v, s, e, tick):
    """returns lo price, histogram for bars s..e-1."""
    lo = 1e18
    hi = -1e18
    for k in range(s, e):
        if lo_b[k] < lo:
            lo = lo_b[k]
        if hi_b[k] > hi:
            hi = hi_b[k]
    n = int(round((hi - lo) / tick)) + 1
    hist = np.zeros(n)
    for k in range(s, e):
        a = int(round((lo_b[k] - lo) / tick))
        b = int(round((hi_b[k] - lo) / tick))
        w = v[k] / (b - a + 1)
        for j in range(a, b + 1):
            hist[j] += w
    return lo, hist


@njit(cache=True)
def value_area(hist, frac):
    n = len(hist)
    mx = hist.max()
    mid = (n - 1) / 2.0
    poc = 0
    best = 1e18
    for j in range(n):
        if hist[j] == mx and abs(j - mid) < best:
            best = abs(j - mid)
            poc = j
    tot = hist.sum()
    acc = hist[poc]
    a = poc
    b = poc
    while acc < frac * tot and (a > 0 or b < n - 1):
        up = hist[b + 1] if b < n - 1 else -1.0
        dn = hist[a - 1] if a > 0 else -1.0
        if up >= dn:
            b += 1
            acc += up
        else:
            a -= 1
            acc += dn
    return poc, a, b


def load_1m():
    df = pd.read_parquet(SRC)
    ts = df.ts
    d = ts.dt.normalize()
    g = d.where(ts.dt.hour < 18, d + pd.Timedelta(days=1))
    wd = g.dt.dayofweek
    g = g.where(wd != 5, g + pd.Timedelta(days=2)).where(wd != 6, g + pd.Timedelta(days=1))
    gm = ((ts - (g - pd.Timedelta(hours=6))).dt.total_seconds() // 60).astype(int)
    keep = (gm >= 0) & (gm < 23 * 60)
    return df[keep].reset_index(drop=True), g[keep].reset_index(drop=True), gm[keep].reset_index(drop=True)


def audit(df, g):
    ts = df.ts
    out = {}
    out["first"], out["last"] = str(ts.iloc[0]), str(ts.iloc[-1])
    out["rows"] = len(df)
    out["duplicates"] = int(ts.duplicated().sum())
    out["bad_ohlc"] = int(((df.High < df[["Open", "Close"]].max(axis=1)) | (df.Low > df[["Open", "Close"]].min(axis=1))).sum())
    out["zero_volume_rows"] = int((df.Volume == 0).sum())
    out["bidask_from"] = str(ts[(df.Bid + df.Ask) > 0].iloc[0])
    days = pd.DatetimeIndex(g.unique())
    bd = pd.bdate_range(days[0], days[-1])
    out["trading_days"] = len(days)
    out["missing_weekdays"] = int(len(bd.difference(days)))
    gaps = ts.diff().dt.total_seconds() / 60
    out["gaps_over_60min_inside_day"] = int(((gaps > 60) & (g.diff().dt.days == 0)).sum())
    out["granularity"] = "1 minute bars, US/Eastern, continuous back-adjusted (no contract field, no VAP, no ticks)"
    return out


def build():
    df, g, gm = load_1m()
    A = audit(df, g)
    o, h, l, c = (df[x].to_numpy(float) for x in ("Open", "High", "Low", "Close"))
    v = df.Volume.to_numpy(float)
    dl = (df.Ask - df.Bid).to_numpy(float)
    gmv = gm.to_numpy()
    gday = g.to_numpy()
    days, first = np.unique(gday, return_index=True)
    last = np.r_[first[1:], len(gday)]
    tp = (h + l + c) / 3
    gd = pd.DatetimeIndex(gday)
    wk = (gd - pd.to_timedelta(gd.dayofweek, unit="D")).to_numpy()
    mo = (gd.year * 12 + gd.month).to_numpy()
    cw = pd.DataFrame({"k": wk, "pv": tp * v, "v": v}).groupby("k")[["pv", "v"]].cumsum()
    cm = pd.DataFrame({"k": mo, "pv": tp * v, "v": v}).groupby("k")[["pv", "v"]].cumsum()
    vw_w = (cw.pv / cw.v).to_numpy()
    vw_m = (cm.pv / cm.v).to_numpy()
    rows, hists = [], {}
    for i, d in enumerate(days):
        s, e = first[i], last[i]
        m = gmv[s:e]
        r = np.flatnonzero((m >= RTH0) & (m < RTH1)) + s
        if len(r) < 200:
            continue
        rs, re_ = r[0], r[-1] + 1
        on = slice(s, rs)
        post = slice(re_, e)
        lo0, hist = profile(l, h, v, rs, re_, TICK)
        poc, a, b = value_area(hist, 0.7)
        hists[pd.Timestamp(d)] = (lo0, hist)
        pv = (tp[rs:re_] * v[rs:re_]).sum()
        vv = v[rs:re_].sum()
        rows.append(dict(date=pd.Timestamp(d), O=o[rs], H=h[rs:re_].max(), L=l[rs:re_].min(), C=c[re_ - 1],
                         hN=h[on].max() if rs > s else np.nan, lN=l[on].min() if rs > s else np.nan,
                         hP=h[post].max() if e > re_ else np.nan, lP=l[post].min() if e > re_ else np.nan,
                         gC=c[e - 1], vol=vv, delta=dl[rs:re_].sum(), vwapD=pv / vv,
                         vwapW=vw_w[re_ - 1], vwapM=vw_m[re_ - 1],
                         POC=lo0 + poc * TICK, VAL=lo0 + a * TICK, VAH=lo0 + b * TICK))
    T = pd.DataFrame(rows).set_index("date")
    return A, T, hists


def enrich(T: pd.DataFrame, hists):
    T = T.copy()
    pc = T.C.shift()
    tr = np.maximum(T.H - T.L, np.maximum((T.H - pc).abs(), (T.L - pc).abs()))
    T["ATR"] = tr.rolling(14).mean()
    T["ret"] = T.C / pc - 1
    T["VAmid"] = (T.VAH + T.VAL) / 2
    T["dPOC"] = T.POC.diff()
    T["dVA"] = T.VAmid.diff()
    T["VM"] = T.dVA / T.ATR
    up = (T.dPOC > 0).astype(int); dn = (T.dPOC < 0).astype(int)
    T["poc_up_streak"] = up.groupby((up == 0).cumsum()).cumsum()
    T["poc_dn_streak"] = dn.groupby((dn == 0).cumsum()).cumsum()
    va_up = (T.dVA > 0).astype(int); va_dn = (T.dVA < 0).astype(int)
    T["va_up_streak"] = va_up.groupby((va_up == 0).cumsum()).cumsum()
    T["va_dn_streak"] = va_dn.groupby((va_dn == 0).cumsum()).cumsum()
    # VA overlap with the previous day, relative to the narrower VA
    inter = np.maximum(0, np.minimum(T.VAH, T.VAH.shift()) - np.maximum(T.VAL, T.VAL.shift()))
    T["overlap"] = inter / np.minimum(T.VAH - T.VAL, (T.VAH - T.VAL).shift()).clip(lower=TICK)
    T["va_width_atr"] = (T.VAH - T.VAL) / T.ATR
    # weekly / monthly VWAP 'slope' = current anchored VWAP vs the previous period's final VWAP
    wk = T.index.to_period("W-FRI"); mo = T.index.to_period("M")
    wfinal = T.vwapW.groupby(wk).last(); mfinal = T.vwapM.groupby(mo).last()
    T["vwapW_prev"] = wfinal.shift().reindex(wk).to_numpy()
    T["vwapM_prev"] = mfinal.shift().reindex(mo).to_numpy()
    T["slopeW"] = (T.vwapW - T.vwapW_prev) / T.ATR
    T["slopeM"] = (T.vwapM - T.vwapM_prev) / T.ATR
    T["BD"] = np.sign(T.C - T.vwapD); T["BW"] = np.sign(T.C - T.vwapW); T["BM"] = np.sign(T.C - T.vwapM)
    T["delta5"] = T.delta.rolling(5).sum()
    T["flow_ok"] = T.index >= "2010-12-27"
    n = 10
    T["TE10"] = (T.C - T.C.shift(n)).abs() / T.C.diff().abs().rolling(n).sum()
    T["rv5"] = T.ret.rolling(5).std() * np.sqrt(252); T["rv20"] = T.ret.rolling(20).std() * np.sqrt(252)
    T["rv_rank"] = T.rv20.rolling(252, min_periods=60).rank(pct=True)
    T["clv"] = (T.C - T.L) / (T.H - T.L).clip(lower=TICK)
    T["vol20"] = T.vol.rolling(20).mean()
    for k in (3, 5, 10, 20, 55):
        T[f"hi{k}"] = T.H.rolling(k).max(); T[f"lo{k}"] = T.L.rolling(k).min()
    T["ema20"] = T.C.ewm(span=20, adjust=False).mean(); T["ema50"] = T.C.ewm(span=50, adjust=False).mean()
    T["ma200"] = T.C.rolling(200).mean()
    T["adx14"] = _adx(T, 14)
    T["rsi2"] = _rsi(T.C, 2)
    # composites: chain of consecutive days with overlap >= 60 % ending at t (L days)
    ov = (T.overlap >= 0.6).to_numpy()
    L = np.ones(len(T), int)
    for i in range(1, len(T)):
        L[i] = L[i - 1] + 1 if ov[i] else 1
    T["comp_len"] = L
    cvah = np.full(len(T), np.nan); cval = cvah.copy(); cpoc = cvah.copy(); chi = cvah.copy(); clo = cvah.copy()
    idx = T.index
    for i in range(len(T)):
        if L[i] < 2:
            continue
        ds = idx[i - L[i] + 1:i + 1]
        lo = min(hists[d][0] for d in ds)
        hi = max(hists[d][0] + (len(hists[d][1]) - 1) * TICK for d in ds)
        Hh = np.zeros(int(round((hi - lo) / TICK)) + 1)
        for d in ds:
            l0, hh = hists[d]
            off = int(round((l0 - lo) / TICK))
            Hh[off:off + len(hh)] += hh
        p, a, b = value_area(Hh, 0.7)
        cpoc[i], cval[i], cvah[i] = lo + p * TICK, lo + a * TICK, lo + b * TICK
        chi[i], clo[i] = T.H.iloc[i - L[i] + 1:i + 1].max(), T.L.iloc[i - L[i] + 1:i + 1].min()
    T["cVAH"], T["cVAL"], T["cPOC"], T["cHigh"], T["cLow"] = cvah, cval, cpoc, chi, clo
    # forward data for entries at the next RTH open
    T["nO"] = T.O.shift(-1)
    return T


def _rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def _adx(T, n):
    up = T.H.diff(); dn = -T.L.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = T.C.shift()
    tr = np.maximum(T.H - T.L, np.maximum((T.H - pc).abs(), (T.L - pc).abs()))
    a = 1 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=T.index).ewm(alpha=a, adjust=False).mean() / atr
    ndi = 100 * pd.Series(ndm, index=T.index).ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).clip(lower=1e-9)
    return dx.ewm(alpha=a, adjust=False).mean()


def load():
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, "rb"))
    A, T, hists = build()
    T = enrich(T, hists)
    out = dict(audit=A, T=T)
    pickle.dump(out, open(CACHE, "wb"), protocol=4)
    return out


if __name__ == "__main__":
    import time
    t = time.time()
    S = load()
    print(S["audit"]); print(len(S["T"]), "days", round(time.time() - t), "s")
    print(S["T"][["O", "H", "L", "C", "POC", "VAL", "VAH", "vwapD", "vwapW", "vwapM", "ATR", "comp_len", "cVAL", "cVAH"]].tail(8))
