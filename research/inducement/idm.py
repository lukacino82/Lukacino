"""Inducement / liquidity-sweep methodology (YouTube video, 'inducement guide'), operationalised on ES 1-minute data 2008-2026.

Video claims (testable parts):
 1. A level where orders are concentrated (previous day / week / month high-low, Asia / Europe / overnight range, 5- and 20-day
    extremes) is broken ('sweep'), stops are taken, breakout traders are invited - then price reverses ('inducement').
 2. A bare sweep is often a trap; a real inducement has a time window (Frankfurt/London/NY open), confluence of levels and
    follow-through confirmation (minor inducement / break of structure).
 3. After a real inducement price moves effortlessly (low resistance): 'tap and go'.
Tests (all numbers in ATR of the previous trading day; cost 0.5 point per trade; ET times; no look-ahead):
 A  race at the sweep: from the trigger price (level +- 0.03 ATR) which barrier comes first, continuation by D or failure by D
    (D = 0.1 / 0.2 / 0.4 ATR); random walk without drift = 50 %; drift-balanced mean of up- and down-sweeps.
 B  reversal trade: price closes back inside the level within W minutes (10/30/60) -> trade against the sweep at that close,
    stop beyond the sweep extreme (+0.02 ATR), target R x risk (R = 1/2/3); win rate vs 1/(1+R) (random walk), net R.
 C  acceptance trade: price stays beyond the level for W minutes -> trade with the breakout, stop 0.1 ATR on the other side of the level.
 D  qualifiers from the video: time window, confluence (another level within 0.1 ATR), volume surge, delta at the sweep, daily trend.
 E  placebo levels: the offset of each level from the session open taken from a random earlier day (same distances and sides,
    no link to real structure).
Periods: discovery 2008-2015, validation 2016-2020, holdout 2021-2026.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "/home/user/Lukacino/research/mega")
import daily as D

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
CACHE = os.path.join(D.DATA, "idm")
TYPES = ["pd", "pw", "pm", "5d", "20d", "asia", "eu", "on"]
TYPE_CZ = {"pd": "včerejší RTH", "pw": "minulý týden", "pm": "minulý měsíc", "5d": "5denní extrém", "20d": "20denní extrém",
           "asia": "Asia range", "eu": "Evropa range", "on": "overnight range"}
KNOWN_SM = {"pd": 0, "pw": 0, "pm": 0, "5d": 0, "20d": 0, "asia": 480, "eu": 930, "on": 930}      # minutes since 18:00 ET
WIN = [("Asie 18-02", 0, 480), ("Frankfurt 02-03", 480, 540), ("Londýn 03-08", 540, 840), ("pre-NY 08-09:30", 840, 930),
       ("NY open 09:30-11", 930, 1020), ("poledne 11-14", 1020, 1200), ("odpoledne 14-17", 1200, 1380)]
PFRAC = 0.03; WS = (10, 30, 60); DS = (0.1, 0.2, 0.4); RS = (1.0, 2.0, 3.0); BUF = 0.02; COST = 0.5


def prepare():
    p = os.path.join(CACHE, "prep.pkl")
    if os.path.exists(p):
        return pd.read_pickle(p)
    d = D.minute()
    t = D.daily_table(d)
    d = d.reset_index(drop=True)
    d["sm"] = (d["mod"] - 1080) % 1440
    days = np.array(sorted(d.gday.unique()))
    starts = np.searchsorted(d.gday.to_numpy(), days, side="left"); ends = np.searchsorted(d.gday.to_numpy(), days, side="right") - 1
    ti = t.index
    # trading-day context (previous completed RTH day)
    prev = np.searchsorted(ti.to_numpy(), days, side="left") - 1
    ok = prev >= 0
    pt = np.where(ok, prev, 0)
    atr = np.where(ok, t.atr.to_numpy()[pt], np.nan)
    ma200 = t.C.rolling(200).mean().to_numpy()[pt]; ma50 = t.C.rolling(50).mean().to_numpy()[pt]
    cprev = t.C.to_numpy()[pt]
    th = t.H; tl = t.L
    LV = np.full((len(days), 16), np.nan)
    pdH = th.to_numpy()[pt]; pdL = tl.to_numpy()[pt]
    wk = ti - pd.to_timedelta(ti.day_of_week, unit="D"); mo = ti.to_period("M")
    pwH = th.groupby(wk).max().shift().reindex(wk).to_numpy(); pwL = tl.groupby(wk).min().shift().reindex(wk).to_numpy()
    pmH = th.groupby(mo).max().shift().reindex(mo).to_numpy(); pmL = tl.groupby(mo).min().shift().reindex(mo).to_numpy()
    # previous COMPLETE week / month relative to each day: take the value of the last trading day's group
    def lastgroup(vals_high, vals_low, key):
        gh = th.groupby(key).max(); gl = tl.groupby(key).min()
        return gh, gl
    # week / month of each Globex day
    dwk = pd.DatetimeIndex(days) - pd.to_timedelta(pd.DatetimeIndex(days).day_of_week, unit="D")
    dmo = pd.DatetimeIndex(days).to_period("M")
    gh = th.groupby(wk).max(); gl = tl.groupby(wk).min()
    ks = gh.index.to_numpy(); j = np.searchsorted(ks, dwk.to_numpy(), side="left") - 1
    pwH = np.where(j >= 0, gh.to_numpy()[np.maximum(j, 0)], np.nan); pwL = np.where(j >= 0, gl.to_numpy()[np.maximum(j, 0)], np.nan)
    gh = th.groupby(mo).max(); gl = tl.groupby(mo).min()
    ks = gh.index.to_timestamp().to_numpy(); j = np.searchsorted(ks, dmo.to_timestamp().to_numpy(), side="left") - 1
    pmH = np.where(j >= 0, gh.to_numpy()[np.maximum(j, 0)], np.nan); pmL = np.where(j >= 0, gl.to_numpy()[np.maximum(j, 0)], np.nan)
    h5 = th.rolling(5).max().to_numpy()[pt]; l5 = tl.rolling(5).min().to_numpy()[pt]
    h20 = th.rolling(20).max().to_numpy()[pt]; l20 = tl.rolling(20).min().to_numpy()[pt]
    g = d.groupby("gday")
    asia = d[d.sm < 480].groupby("gday").agg(h=("High", "max"), l=("Low", "min")).reindex(days)
    eu = d[(d.sm >= 480) & (d.sm < 930)].groupby("gday").agg(h=("High", "max"), l=("Low", "min")).reindex(days)
    on = d[d.sm < 930].groupby("gday").agg(h=("High", "max"), l=("Low", "min")).reindex(days)
    hi = {"pd": pdH, "pw": pwH, "pm": pmH, "5d": h5, "20d": h20, "asia": asia.h.to_numpy(), "eu": eu.h.to_numpy(), "on": on.h.to_numpy()}
    lo = {"pd": pdL, "pw": pwL, "pm": pmL, "5d": l5, "20d": l20, "asia": asia.l.to_numpy(), "eu": eu.l.to_numpy(), "on": on.l.to_numpy()}
    for i, ty in enumerate(TYPES):
        LV[:, 2 * i] = hi[ty]; LV[:, 2 * i + 1] = lo[ty]
    LV[~ok] = np.nan
    O0 = d.Open.to_numpy()[starts]
    out = dict(d=d, days=days, starts=starts, ends=ends, atr=atr, ma200=ma200, ma50=ma50, cprev=cprev, LV=LV, O0=O0)
    os.makedirs(CACHE, exist_ok=True)
    pd.to_pickle(out, p)
    return out


@njit(cache=True)
def events(H, L, C, sm, starts, ends, LV, KN, SD, atr, pfrac, Ws, Ds):
    nd, nk = LV.shape
    cap = nd * nk
    nW = len(Ws); nD = len(Ds)
    day = np.full(cap, -1, np.int32); kk = np.zeros(cap, np.int8); trig = np.zeros(cap, np.int32)
    rec = np.full((cap, nW), -1, np.int32); ext = np.zeros((cap, nW)); acc = np.full((cap, nW), -1, np.int32)
    race = np.zeros((cap, nD), np.int8)
    m = 0
    for d in range(nd):
        a = atr[d]
        if not (a > 0):
            continue
        for k in range(nk):
            lv = LV[d, k]
            if np.isnan(lv):
                continue
            s = SD[k]; p = pfrac * a; e = ends[d]
            j0 = -1
            for j in range(starts[d] + 1, e + 1):
                if sm[j] < KN[k]:
                    continue
                if s == 1:
                    if C[j - 1] < lv and H[j] >= lv + p:
                        j0 = j; break
                else:
                    if C[j - 1] > lv and L[j] <= lv - p:
                        j0 = j; break
            if j0 < 0:
                continue
            day[m] = d; kk[m] = k; trig[m] = j0
            for w in range(nW):
                W = Ws[w]; best = H[j0] if s == 1 else L[j0]; found = -1
                for q in range(j0 + 1, min(j0 + W, e) + 1):
                    if s == 1:
                        if H[q] > best: best = H[q]
                        if C[q] < lv:
                            found = q; break
                    else:
                        if L[q] < best: best = L[q]
                        if C[q] > lv:
                            found = q; break
                rec[m, w] = found; ext[m, w] = best
                if found < 0 and j0 + W <= e:
                    q = j0 + W
                    if (s == 1 and C[q] > lv) or (s == -1 and C[q] < lv):
                        acc[m, w] = q
            tpx = lv + s * p
            for di in range(nD):
                up = tpx + s * Ds[di] * a; dn = tpx - s * Ds[di] * a; r = 0
                for q in range(j0 + 1, e + 1):
                    if s == 1:
                        hu = H[q] >= up; hd = L[q] <= dn
                    else:
                        hu = L[q] <= up; hd = H[q] >= dn
                    if hu and hd:
                        break
                    if hu:
                        r = 1; break
                    if hd:
                        r = -1; break
                race[m, di] = r
            m += 1
    return day[:m], kk[:m], trig[:m], rec[:m], ext[:m], acc[:m], race[:m]


@njit(cache=True)
def trade(H, L, C, ent, side, sl, tp, end):
    """first passage after entry; returns +R multiple of the risk is computed outside: 1 win, -1 loss, 0 timeout; final pnl in points"""
    n = len(ent); res = np.zeros(n, np.int8); pnl = np.zeros(n)
    for k in range(n):
        i = ent[k]; s = side[k]; r = 0; px = C[end[k]]
        for q in range(i + 1, end[k] + 1):
            if s == 1:
                hs = L[q] <= sl[k]; ht = H[q] >= tp[k]
            else:
                hs = H[q] >= sl[k]; ht = L[q] <= tp[k]
            if hs:
                r = -1; px = sl[k]; break
            if ht:
                r = 1; px = tp[k]; break
        res[k] = r; pnl[k] = (px - C[i]) * s
    return res, pnl


def build(placebo=False, seed=0):
    P = prepare()
    d = P["d"]; H = d.High.to_numpy(); L = d.Low.to_numpy(); C = d.Close.to_numpy(); V = d.Volume.to_numpy().astype(float)
    dl = d.delta.to_numpy(); sm = d.sm.to_numpy().astype(np.int32)
    LV = P["LV"].copy(); atr = P["atr"]; O0 = P["O0"]
    SD = np.array([1, -1] * len(TYPES), np.int8); KN = np.repeat([KNOWN_SM[t] for t in TYPES], 2).astype(np.int32)
    if placebo:
        rng = np.random.default_rng(seed); nd = len(LV)
        jj = np.arange(nd) - rng.integers(5, 61, nd)
        off = (LV[np.maximum(jj, 0)] - O0[np.maximum(jj, 0), None]) / atr[np.maximum(jj, 0), None]
        LV = O0[:, None] + off * atr[:, None]
        LV[jj < 0] = np.nan
    day, kk, trig, rec, ext, acc, race = events(H, L, C, sm, P["starts"], P["ends"], LV, KN, SD, np.nan_to_num(atr), PFRAC,
                                                np.array(WS, np.int64), np.array(DS))
    E = pd.DataFrame({"day": day, "k": kk, "trig": trig})
    E["typ"] = [TYPES[k // 2] for k in kk]; E["side"] = np.where(kk % 2 == 0, 1, -1)
    E["lvl"] = LV[day, kk]; E["atr"] = atr[day]; E["ts"] = d.ts.to_numpy()[trig]; E["sm"] = sm[trig]
    E["gday"] = P["days"][day]
    E["win"] = np.select([E.sm.between(a, b - 1) for _, a, b in WIN], [n for n, _, _ in WIN], "mimo")
    E["trend"] = np.where(P["cprev"][day] > P["ma200"][day], 1, np.where(P["cprev"][day] < P["ma200"][day], -1, 0))
    # qualifiers
    v30 = pd.Series(V).rolling(30).mean().shift().to_numpy()
    E["relvol"] = V[trig] / v30[trig]
    E["delta_rel"] = np.where(d.ts.dt.year.to_numpy()[trig] >= 2011, dl[trig] / np.maximum(V[trig], 1), np.nan) * E.side
    cnt = np.zeros(len(E), int)
    for sgn in (1, -1):
        mk = (E.side == sgn).to_numpy()
        cols = [2 * i + (0 if sgn == 1 else 1) for i in range(len(TYPES))]
        sub = LV[day[mk]][:, cols]; me = E.lvl.to_numpy()[mk][:, None]
        knw = np.array([KNOWN_SM[t] for t in TYPES])[None, :] <= E.sm.to_numpy()[mk][:, None]
        near = (np.abs(sub - me) <= 0.1 * E.atr.to_numpy()[mk][:, None]) & knw
        cnt[mk] = near.sum(axis=1) - 1
    E["konfluence"] = np.maximum(cnt, 0)
    for i, D_ in enumerate(DS):
        E[f"race{D_}"] = race[:, i]
    end_idx = P["ends"][day]
    rows = []
    for w, W in enumerate(WS):
        okr = rec[:, w] >= 0
        ent = rec[okr, w].astype(np.int64); s_ = -E.side.to_numpy()[okr]          # trade against the sweep
        sl = ext[okr, w] + E.side.to_numpy()[okr] * BUF * E.atr.to_numpy()[okr]
        risk = np.abs(C[ent] - sl); atr_e = E.atr.to_numpy()[okr]
        good = (risk >= 0.03 * atr_e) & (risk <= 0.6 * atr_e)
        for R in RS:
            tp = C[ent] + s_ * R * risk
            res, pnl = trade(H, L, C, ent, s_.astype(np.int64), sl, tp, end_idx[okr].astype(np.int64))
            rows.append(pd.DataFrame({"e": np.flatnonzero(okr), "kind": "reverzni", "W": W, "R": R, "res": res, "pnl_pts": pnl, "risk_pts": risk,
                                      "risk_atr": risk / atr_e, "good": good, "entry": ent, "sidetr": s_}))
        oka = acc[:, w] >= 0
        ent = acc[oka, w].astype(np.int64); s_ = E.side.to_numpy()[oka]
        sl = E.lvl.to_numpy()[oka] - s_ * 0.1 * E.atr.to_numpy()[oka]
        risk = np.abs(C[ent] - sl); atr_e = E.atr.to_numpy()[oka]
        good = (risk >= 0.03 * atr_e) & (risk <= 0.6 * atr_e)
        for R in RS:
            tp = C[ent] + s_ * R * risk
            res, pnl = trade(H, L, C, ent, s_.astype(np.int64), sl, tp, end_idx[oka].astype(np.int64))
            rows.append(pd.DataFrame({"e": np.flatnonzero(oka), "kind": "akceptace", "W": W, "R": R, "res": res, "pnl_pts": pnl, "risk_pts": risk,
                                      "risk_atr": risk / atr_e, "good": good, "entry": ent, "sidetr": s_}))
    T = pd.concat(rows, ignore_index=True)
    T = T[T.good].copy()
    T["Rnet"] = np.where(T.res == 1, T.R, np.where(T.res == -1, -1.0, T.pnl_pts / T.risk_pts)) - COST / T.risk_pts
    T["null_win"] = 1 / (1 + T.R)
    return E, T


if __name__ == "__main__":
    import time
    t0 = time.time()
    E, T = build(); E.to_parquet(os.path.join(CACHE, "E_real.parquet")); T.to_parquet(os.path.join(CACHE, "T_real.parquet"))
    print("real", len(E), len(T), round(time.time() - t0), "s")
    for s in (1, 2, 3):
        Ep, Tp = build(True, s); Ep.to_parquet(os.path.join(CACHE, f"E_pl{s}.parquet")); Tp.to_parquet(os.path.join(CACHE, f"T_pl{s}.parquet"))
        print("placebo", s, len(Ep), len(Tp), round(time.time() - t0), "s")
