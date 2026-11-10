"""Mega scan, daily layer: daily table, ~200 features, signal bank and outcomes (ES back-adjusted 1-min, 2008-05..2026-09).

Decision time = last RTH bar of the day (15:59 ET; early close on half days). Everything is known at that close.
Signals: every continuous feature -> rolling 252-day percentile rank (past only) -> 9 bins; plus calendar, streak,
candle, pattern, level and control ('random') signals. Outcomes from the close, in units of ATR14:
  horizons: overnight, next RTH, close-to-close 1/2/3/5/10/20 days;
  TP/SL first passage on 1-minute bars: SL 0.5/1/1.5/2/3 ATR x RRR 0.5/1/1.5/2/3/5, long and short, max 10 days,
  cost 0.5 point, same-bar SL+TP = loss.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from numba import njit, prange

DATA = "/tmp/claude-0/data"
CACHE = os.path.join(DATA, "mega")
COST = 0.5
SLS = np.array([0.5, 1.0, 1.5, 2.0, 3.0])
RRRS = np.array([0.5, 1.0, 1.5, 2.0, 3.0, 5.0])
HOLD = 10


def minute():
    d = pd.read_parquet(os.path.join(DATA, "es2008.parquet"))
    d["gday"] = (d.ts + pd.Timedelta(hours=6)).dt.normalize()
    d["mod"] = d.ts.dt.hour * 60 + d.ts.dt.minute
    d["delta"] = (d.Ask - d.Bid).astype(float)
    return d


def daily_table(d):
    rth = d[(d["mod"] >= 570) & (d["mod"] < 960)]
    g = rth.groupby("gday")
    t = g.agg(O=("Open", "first"), H=("High", "max"), L=("Low", "min"), C=("Close", "last"), V=("Volume", "sum"),
              dlt=("delta", "sum"), nb=("Close", "size"))
    t["e"] = g.apply(lambda x: x.index[-1], include_groups=False)
    t["o_idx"] = g.apply(lambda x: x.index[0], include_groups=False)
    on = d[(d["mod"] >= 1080) | (d["mod"] < 570)].groupby("gday").agg(onH=("High", "max"), onL=("Low", "min"))
    t = t.join(on)
    for nm, m in (("p1030", 629), ("p1200", 719), ("p1500", 899)):
        t[nm] = rth[rth["mod"] <= m].groupby("gday").Close.last()
    t["tH"] = g.apply(lambda x: x["mod"].to_numpy()[np.argmax(x.High.to_numpy())] - 570, include_groups=False)
    t["tL"] = g.apply(lambda x: x["mod"].to_numpy()[np.argmin(x.Low.to_numpy())] - 570, include_groups=False)
    # VWAPs (typical price) for day / week / month, value at the last RTH bar
    tp = ((d.High + d.Low + d.Close) / 3).to_numpy(); v = d.Volume.to_numpy().astype(float)
    wk = (d.gday - pd.to_timedelta(d.gday.dt.day_of_week, unit="D")).to_numpy()
    mo = d.gday.dt.to_period("M").astype(str).to_numpy()
    for nm, key in (("d", d.gday.to_numpy()), ("w", wk), ("m", mo)):
        df = pd.DataFrame({"k": key, "pv": tp * v, "p2v": tp * tp * v, "v": v}).groupby("k", sort=False)
        cv = df.v.cumsum().to_numpy(); cv = np.where(cv > 0, cv, np.nan)
        vw = df.pv.cumsum().to_numpy() / cv
        sd = np.sqrt(np.maximum(df.p2v.cumsum().to_numpy() / cv - vw * vw, 0))
        t["vw_" + nm] = vw[t.e.to_numpy()]; t["sd_" + nm] = sd[t.e.to_numpy()]
        if nm == "d":
            x = pd.Series(np.sign(d.Close.to_numpy() - vw)).where(((d["mod"] >= 570) & (d["mod"] < 960)).to_numpy())
            t["nx"] = (x.diff().abs() > 1).groupby(d.gday.to_numpy()).sum()
    t = t[t.nb >= 120].copy()
    c = pd.read_parquet(os.path.join(DATA, "bcl_cash.parquet"))
    cc = c[(c.ts.dt.hour * 60 + c.ts.dt.minute < 960) & (c.ts.dt.hour * 60 + c.ts.dt.minute >= 570)]
    t["cash"] = cc.groupby(cc.ts.dt.normalize()).C.last()
    t["cash"] = t.cash.fillna(t.C)            # last 2 days: cash series ends 2 days earlier
    pc = t.C.shift()
    tr = np.maximum(t.H - t.L, np.maximum((t.H - pc).abs(), (t.L - pc).abs()))
    t["atr"] = tr.rolling(14).mean()
    return t.dropna(subset=["atr"])


def rsi(c, n):
    dlt = c.diff()
    up = dlt.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-dlt.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def features(t):
    F = {}
    C, O, H, L, A, cc = t.C, t.O, t.H, t.L, t.atr, t.cash
    r1 = C.diff() / A; pr = cc.pct_change()
    for k in (1, 2, 3, 5, 10, 20, 60, 120, 250):
        F[f"ret{k}"] = (C - C.shift(k)) / A
    ma = {n: C.rolling(n).mean() for n in (5, 10, 20, 50, 100, 200)}
    for n in ma:
        F[f"dma{n}"] = (C - ma[n]) / A
    F["ma50_200"] = (ma[50] - ma[200]) / A; F["ma10_50"] = (ma[10] - ma[50]) / A
    for n in (2, 3, 5, 14):
        F[f"rsi{n}"] = rsi(C, n)
    rng = (H - L).replace(0, np.nan)
    F["ibs"] = (C - L) / rng; F["rng"] = rng / A; F["rng3"] = rng.rolling(3).mean() / A; F["rng5"] = rng.rolling(5).mean() / A
    tr = np.maximum(H - L, np.maximum((H - C.shift()).abs(), (L - C.shift()).abs()))
    F["atr5_20"] = tr.rolling(5).mean() / tr.rolling(20).mean(); F["atr14_100"] = A / tr.rolling(100).mean()
    F["atrpct"] = A / cc
    for n in (5, 20, 60):
        F[f"rv{n}"] = pr.rolling(n).std()
    F["rv5_60"] = F["rv5"] / F["rv60"]
    for n in (5, 10, 20, 60, 252):
        F[f"dd{n}"] = cc / cc.rolling(n).max() - 1
    for n in (5, 20, 60):
        F[f"ru{n}"] = cc / cc.rolling(n).min() - 1
    F["gap"] = (O - C.shift()) / A.shift(); F["onrng"] = (t.onH - t.onL) / A
    F["opos"] = (O - L.shift()) / (H.shift() - L.shift()).replace(0, np.nan)
    F["fh"] = (t.p1030 - O) / A; F["lh"] = (C - t.p1500) / A; F["mid"] = (t.p1500 - t.p1030) / A; F["oc"] = (C - O) / A
    F["am"] = (t.p1200 - O) / A; F["pm"] = (C - t.p1200) / A
    for nm in "dwm":
        F["vz_" + nm] = (C - t["vw_" + nm]) / t["sd_" + nm].replace(0, np.nan)
    F["vr20"] = t.V / t.V.rolling(20).mean(); F["v5_60"] = t.V.rolling(5).mean() / t.V.rolling(60).mean()
    dl = (t.dlt / t.V).where(t.index >= "2011-01-01")
    F["dl1"] = dl; F["dl5"] = dl.rolling(5).mean(); F["dl20"] = dl.rolling(20).mean()
    F["dldiv"] = dl.rolling(252).rank(pct=True) - F["oc"].rolling(252).rank(pct=True)
    F["er"] = (C - O).abs() / rng
    for n in (10, 20):
        F[f"ker{n}"] = (C - C.shift(n)).abs() / C.diff().abs().rolling(n).sum()
    F["ac20"] = pr.rolling(20).corr(pr.shift()); F["ac60"] = pr.rolling(60).corr(pr.shift())
    F["sk20"] = pr.rolling(20).skew(); F["sk60"] = pr.rolling(60).skew(); F["ku60"] = pr.rolling(60).kurt()
    up = (r1 > 0).astype(float)
    for n in (5, 10, 20):
        F[f"up{n}"] = up.rolling(n).sum()
    F["minr5"] = r1.rolling(5).min(); F["minr20"] = r1.rolling(20).min(); F["maxr5"] = r1.rolling(5).max(); F["maxr20"] = r1.rolling(20).max()
    for n in (20, 252):
        F[f"dsh{n}"] = C.rolling(n).apply(lambda x: len(x) - 1 - np.argmax(x), raw=True)
        F[f"dsl{n}"] = C.rolling(n).apply(lambda x: len(x) - 1 - np.argmin(x), raw=True)
    F["uw"] = (H - np.maximum(O, C)) / rng; F["lw"] = (np.minimum(O, C) - L) / rng
    sd20 = C.rolling(20).std(); F["pctb"] = (C - ma[20]) / (2 * sd20)
    for n in (5, 14, 20, 55):
        hh = H.rolling(n).max(); ll = L.rolling(n).min(); F[f"st{n}"] = (C - ll) / (hh - ll).replace(0, np.nan)
    tpz = (H + L + C) / 3; F["cci20"] = (tpz - tpz.rolling(20).mean()) / (0.015 * (tpz - tpz.rolling(20).mean()).abs().rolling(20).mean())
    macd = C.ewm(span=12, adjust=False).mean() - C.ewm(span=26, adjust=False).mean()
    F["macd"] = macd / A; F["macdh"] = (macd - macd.ewm(span=9, adjust=False).mean()) / A
    upm = H.diff(); dnm = -L.diff()
    pdm = np.where((upm > dnm) & (upm > 0), upm, 0.0); mdm = np.where((dnm > upm) & (dnm > 0), dnm, 0.0)
    atrw = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=t.index).ewm(alpha=1 / 14, adjust=False).mean() / atrw
    mdi = 100 * pd.Series(mdm, index=t.index).ewm(alpha=1 / 14, adjust=False).mean() / atrw
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    F["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean(); F["didiff"] = pdi - mdi
    F["vr5"] = (cc.pct_change(5).rolling(60).var()) / (5 * pr.rolling(60).var())
    F["nx"] = t.nx; F["tH"] = t.tH; F["tL"] = t.tL; F["offh"] = (H - C) / A; F["offl"] = (C - L) / A
    wk = t.index - pd.to_timedelta(t.index.day_of_week, unit="D")
    wopen = C.groupby(wk).transform("first"); F["wtd"] = (C - C.shift().groupby(wk).transform("first").fillna(wopen)) / A
    mk = t.index.to_period("M"); F["mtd"] = (C - C.shift().groupby(mk).transform("first")) / A
    yk = t.index.year; F["ytd"] = cc / cc.shift().groupby(yk).transform("first") - 1
    wH = H.groupby(wk).cummax(); wL = L.groupby(wk).cummin(); F["wpos"] = (C - wL) / (wH - wL).replace(0, np.nan)
    mH = H.groupby(mk).cummax(); mL = L.groupby(mk).cummin(); F["mpos"] = (C - mL) / (mH - mL).replace(0, np.nan)
    F["pmret"] = cc.groupby(mk).last().pct_change().reindex(mk).shift(0).to_numpy() if False else pd.Series(
        cc.groupby(mk).last().pct_change().shift().reindex(mk).to_numpy(), index=t.index)
    F["pwret"] = pd.Series(cc.groupby(wk).last().pct_change().shift().reindex(wk).to_numpy(), index=t.index)
    F = pd.DataFrame(F, index=t.index)
    lag = ["ret1", "ibs", "rng", "gap", "dl1", "fh", "lh", "vr20", "oc", "rsi2", "vz_d", "vz_w", "er", "uw", "lw", "onrng", "ret3",
           "dma5", "offh", "offl", "am", "pm", "mid", "nx", "atr5_20", "ret5", "dd5", "st5", "vz_m", "pctb"]
    for c in lag:
        F[c + "_l1"] = F[c].shift(1)
    for c in lag[:15]:
        F[c + "_l2"] = F[c].shift(2)
    return F


def categorical(t, F):
    S = {}
    idx = t.index
    C, O, H, L, A, cc = t.C, t.O, t.H, t.L, t.atr, t.cash
    r1 = C.diff() / A
    names = ["Po", "Ut", "St", "Ct", "Pa"]
    for k in range(5):
        S[f"den={names[k]}"] = idx.day_of_week == k
    nxt = pd.Series(idx, index=idx).shift(-1); prv = pd.Series(idx, index=idx).shift(1)
    for k in range(5):
        S[f"zitra={names[k]}"] = (nxt.dt.day_of_week == k).to_numpy()
    for m in range(1, 13):
        S[f"mesic={m}"] = idx.month == m
    mk = idx.to_period("M")
    tdm = pd.Series(1, index=idx).groupby(mk).cumsum(); tdl = pd.Series(1, index=idx)[::-1].groupby(mk[::-1]).cumsum()[::-1]
    for k in range(1, 6):
        S[f"obch_den_mesice={k}"] = (tdm == k).to_numpy(); S[f"do_konce_mesice={k}"] = (tdl == k).to_numpy()
    S["prelom_mesice(-2..+3)"] = ((tdl <= 2) | (tdm <= 3)).to_numpy()
    wom = (idx.day - 1) // 7 + 1
    for k in range(1, 6):
        S[f"tyden_mesice={k}"] = wom == k
    S["konec_kvartalu_3d"] = ((tdl <= 3) & idx.month.isin([3, 6, 9, 12])).to_numpy()
    third_fri = (idx.day_of_week == 4) & (idx.day >= 15) & (idx.day <= 21)
    S["opex_den"] = third_fri
    wk = idx - pd.to_timedelta(idx.day_of_week, unit="D")
    S["opex_tyden"] = pd.Series(third_fri, index=idx).groupby(wk).transform("max").to_numpy().astype(bool)
    gap_next = (nxt - pd.Series(idx, index=idx)).dt.days; gap_prev = (pd.Series(idx, index=idx) - prv).dt.days
    S["pred_svatkem"] = ((gap_next > 1) & (idx.day_of_week != 4) | (gap_next > 3)).to_numpy()
    S["po_svatku"] = ((gap_prev > 1) & (idx.day_of_week != 0) | (gap_prev > 3)).to_numpy()
    S["pulden"] = (t.nb < 300).to_numpy()
    for k in range(4):
        S[f"prez_cyklus={k}"] = idx.year % 4 == k
    S["prvni_pulka_mesice"] = idx.day <= 15
    dn = (r1 < 0); upd = (r1 > 0)
    def streak(b):
        g = (~b).cumsum(); return b.groupby(g).cumsum()
    sd_, su_ = streak(dn), streak(upd)
    for k in range(1, 7):
        S[f"pokles_v_rade>={k}"] = (sd_ >= k).to_numpy(); S[f"rust_v_rade>={k}"] = (su_ >= k).to_numpy()
        S[f"pokles_v_rade={k}"] = (sd_ == k).to_numpy(); S[f"rust_v_rade={k}"] = (su_ == k).to_numpy()
    sg = upd.astype(int)
    code = sum(sg.shift(k).fillna(0).astype(int) * (2 ** k) for k in range(5))
    for k in range(32):
        S["5dni=" + format(k, "05b")[::-1].replace("1", "R").replace("0", "P")] = (code == k).to_numpy()
    big = (r1.abs() > 0.5).astype(int); c4 = sg * 2 + big
    code3 = sum(c4.shift(k).fillna(0).astype(int) * (4 ** k) for k in range(3))
    for k in range(64):
        S[f"3dni_velikost={k}"] = (code3 == k).to_numpy()
    rng = H - L
    S["inside"] = ((H <= H.shift()) & (L >= L.shift())).to_numpy(); S["outside"] = ((H > H.shift()) & (L < L.shift())).to_numpy()
    S["NR4"] = (rng <= rng.rolling(4).min()).to_numpy(); S["NR7"] = (rng <= rng.rolling(7).min()).to_numpy()
    S["WR7"] = (rng >= rng.rolling(7).max()).to_numpy()
    S["doji"] = ((C - O).abs() < 0.1 * rng).to_numpy()
    S["kladivo"] = (F.lw > 0.6).to_numpy(); S["padajici_hvezda"] = (F.uw > 0.6).to_numpy()
    S["byci_pohlceni"] = ((C > O) & (C.shift() < O.shift()) & (C > O.shift()) & (O < C.shift())).to_numpy()
    S["medvedi_pohlceni"] = ((C < O) & (C.shift() > O.shift()) & (C < O.shift()) & (O > C.shift())).to_numpy()
    for x in (0.25, 0.5, 1.0):
        S[f"gap_nahoru>{x}"] = (F.gap > x).to_numpy(); S[f"gap_dolu>{x}"] = (F.gap < -x).to_numpy()
    S["gap_nahoru_vyplnen"] = ((F.gap > 0.1) & (L <= C.shift())).to_numpy(); S["gap_dolu_vyplnen"] = ((F.gap < -0.1) & (H >= C.shift())).to_numpy()
    S["gap_nahoru_nevyplnen"] = ((F.gap > 0.1) & (L > C.shift())).to_numpy(); S["gap_dolu_nevyplnen"] = ((F.gap < -0.1) & (H < C.shift())).to_numpy()
    for n in (5, 10, 20, 50, 100, 252):
        S[f"nove_max_{n}"] = (C >= C.rolling(n).max()).to_numpy(); S[f"nove_min_{n}"] = (C <= C.rolling(n).min()).to_numpy()
        S[f"high_nad_{n}d_high"] = (H > H.shift().rolling(n).max()).to_numpy(); S[f"low_pod_{n}d_low"] = (L < L.shift().rolling(n).min()).to_numpy()
    for n in (5, 10, 20, 50, 100, 200):
        m = C.rolling(n).mean(); S[f"nad_MA{n}"] = (C > m).to_numpy(); S[f"pod_MA{n}"] = (C < m).to_numpy()
        S[f"MA{n}_roste"] = (m > m.shift(5)).to_numpy()
    S["zlaty_kriz"] = (C.rolling(50).mean() > C.rolling(200).mean()).to_numpy(); S["smrtici_kriz"] = (C.rolling(50).mean() < C.rolling(200).mean()).to_numpy()
    for m in (100, 50):
        d_ = (cc % m); d_ = np.minimum(d_, m - d_)
        S[f"u_kulate_{m}"] = (d_ < 0.25 * A).to_numpy()
        S[f"prurazil_{m}_nahoru"] = ((cc // m) > (cc.shift() // m)).to_numpy(); S[f"prurazil_{m}_dolu"] = ((cc // m) < (cc.shift() // m)).to_numpy()
    ph = ((idx - pd.Timestamp("2000-01-06 18:14")).total_seconds() / 86400 / 29.530588) % 1
    S["nov"] = (ph < 0.05) | (ph > 0.95); S["uplnek"] = np.abs(ph - 0.5) < 0.05; S["dorusta"] = ph < 0.5
    S["kontrola_sudy_den_roku"] = idx.day_of_year % 2 == 0
    S["kontrola_ciferny_soucet_lichy"] = np.array([sum(map(int, x.strftime("%Y%m%d"))) % 2 for x in idx]) == 1
    rs = np.random.default_rng(1)
    for k in range(10):
        S[f"kontrola_nahodny_{k}"] = rs.random(len(idx)) < (0.1 + 0.08 * k)
    for nm, col in (("high", t.tH), ("low", t.tL)):
        S[f"{nm}_v_prvnich_30m"] = (col < 30).to_numpy(); S[f"{nm}_30_120m"] = ((col >= 30) & (col < 120)).to_numpy()
        S[f"{nm}_uprostred"] = ((col >= 120) & (col < 330)).to_numpy(); S[f"{nm}_v_posledni_hodine"] = (col >= 330).to_numpy()
    S["close_nad_vcerejsim_high"] = (C > H.shift()).to_numpy(); S["close_pod_vcerejsim_low"] = (C < L.shift()).to_numpy()
    S["close_nad_open"] = (C > O).to_numpy(); S["close_pod_open"] = (C < O).to_numpy()
    on = np.sign(F.gap); rt = np.sign(C - O)
    for a, an in ((1, "noc+"), (-1, "noc-")):
        for b, bn in ((1, "den+"), (-1, "den-")):
            S[an + bn] = ((on == a) & (rt == b)).to_numpy()
    wH = H.groupby(wk).max().shift().reindex(wk).to_numpy(); wL = L.groupby(wk).min().shift().reindex(wk).to_numpy()
    S["nad_high_min_tydne"] = (C.to_numpy() > wH); S["pod_low_min_tydne"] = (C.to_numpy() < wL)
    S["uvnitr_range_min_tydne"] = (C.to_numpy() <= wH) & (C.to_numpy() >= wL)
    mH = H.groupby(mk).max().shift().reindex(mk).to_numpy(); mL = L.groupby(mk).min().shift().reindex(mk).to_numpy()
    S["nad_high_min_mesice"] = (C.to_numpy() > mH); S["pod_low_min_mesice"] = (C.to_numpy() < mL)
    return pd.DataFrame({k: np.asarray(v, bool) for k, v in S.items()}, index=idx)


BINS = [("<=5", 0, .05), ("<=10", 0, .10), ("<=20", 0, .20), ("<=35", 0, .35), ("35-65", .35, .65), (">=65", .65, 1.01),
        (">=80", .80, 1.01), (">=90", .90, 1.01), (">=95", .95, 1.01)]


def signal_bank(F, Cat):
    R = F.rolling(252, min_periods=200).rank(pct=True)
    cols = {}
    for c in F.columns:
        r = R[c].to_numpy()
        for nm, lo, hi in BINS:
            if lo == 0:
                cols[f"{c}{nm}"] = r <= hi
            elif hi > 1:
                cols[f"{c}{nm}"] = r >= lo
            else:
                cols[f"{c}:{nm}"] = (r > lo) & (r < hi)
    B = pd.concat([pd.DataFrame(cols, index=F.index), Cat], axis=1)
    return B


@njit(parallel=True, cache=True)
def tpsl(H, L, C, ent, end, atr, sls, tps):
    n = len(ent); ns = len(sls); nt = len(tps)
    big = 1 << 30
    tsl = np.full((n, 2, ns), big, np.int32); ttp = np.full((n, 2, nt), big, np.int32); fin = np.zeros(n)
    for k in prange(n):
        e = ent[k]; p = C[e]; a = atr[k]
        ks0 = 0; ks1 = 0; kt0 = 0; kt1 = 0
        for j in range(e + 1, end[k] + 1):
            up = (H[j] - p) / a; dn = (p - L[j]) / a
            while ks0 < ns and dn >= sls[ks0]:
                tsl[k, 0, ks0] = j - e; ks0 += 1          # long stop
            while ks1 < ns and up >= sls[ks1]:
                tsl[k, 1, ks1] = j - e; ks1 += 1          # short stop
            while kt0 < nt and up >= tps[kt0]:
                ttp[k, 0, kt0] = j - e; kt0 += 1          # long target
            while kt1 < nt and dn >= tps[kt1]:
                ttp[k, 1, kt1] = j - e; kt1 += 1
        fin[k] = (C[end[k]] - p) / a
    return tsl, ttp, fin


def outcomes(t, d):
    n = len(t); e = t.e.to_numpy(); A = t.atr.to_numpy(); C = t.C.to_numpy(); O = t.O.to_numpy()
    Y = {}
    sh = lambda x, k: np.r_[x[k:], np.full(k, np.nan)]
    Y["noc (close->open)"] = (sh(O, 1) - C) / A
    Y["dalsi RTH (open->close)"] = (sh(C, 1) - sh(O, 1)) / A
    for k in (1, 2, 3, 5, 10, 20):
        Y[f"drzeni {k}d"] = (sh(C, k) - C) / A
    end = np.r_[e[HOLD:], np.full(HOLD, -1)]
    ok = end > 0
    tps = np.unique(np.round(np.outer(SLS, RRRS).ravel(), 4))
    Hm = d.High.to_numpy(); Lm = d.Low.to_numpy(); Cm = d.Close.to_numpy()
    tsl, ttp, fin = tpsl(Hm, Lm, Cm, e[ok].astype(np.int64), end[ok].astype(np.int64), A[ok], SLS, tps)
    for side, sn in ((0, "long"), (1, "short")):
        for i, s in enumerate(SLS):
            for r in RRRS:
                j = int(np.searchsorted(tps, round(s * r, 4)))
                a = tsl[:, side, i]; b = ttp[:, side, j]
                win = b < a; loss = (a <= b) & (a < (1 << 30))
                y = np.where(win, s * r, np.where(loss, -s, fin * (1 if side == 0 else -1))) - COST / A[ok]
                full = np.full(n, np.nan); full[ok] = y
                Y[f"{sn} SL{s:g} RRR{r:g}"] = full
    return pd.DataFrame(Y, index=t.index)


def build():
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "daily.pkl")
    if os.path.exists(p):
        return pd.read_pickle(p)
    d = minute(); t = daily_table(d)
    F = features(t); Cat = categorical(t, F); B = signal_bank(F, Cat); Y = outcomes(t, d)
    out = dict(t=t, F=F, B=B, Y=Y)
    pd.to_pickle(out, p)
    return out


if __name__ == "__main__":
    import time
    t0 = time.time(); o = build()
    print(round(time.time() - t0), "s", o["t"].shape, o["F"].shape, o["B"].shape, o["Y"].shape, o["t"].index[[0, -1]])
    print(o["Y"].describe().T[["count", "mean", "std"]].round(3).head(12))
    print(o["B"].mean().describe().round(3))
