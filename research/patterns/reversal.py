"""Block 6b - what precedes real intraday reversals.
Event: in RTH (09:45-15:00) price makes a new 60-minute low (high). It is a 'real reversal' if within 120 minutes the
price moves 0.3 ATR away from that extreme before trading 0.1 ATR beyond it. Features known at the event bar:
CD change over 30 min (divergence), price change over 30 min, distance from the daily VWAP in SD, distance to the
previous day low/high and previous day POC (ATR), relative volume of the last 5 minutes, time of day, range of the
day so far / ATR, sign of the day CD, position vs weekly VWAP. Univariate reversal rates by quintile, then a
walk-forward LightGBM (train on all years before, test one year) and a trade test on the top 10 % predictions:
entry at the close, SL 0.1 ATR beyond the extreme, TP 0.3 ATR from the extreme, cost 0.5 point.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "/home/user/Lukacino/research/delta_vwap")
import prep as P
from trade import summarize
from vwap import day_end

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


@njit(cache=True)
def label(H, L, ext, side, atr, idx, end):
    y = np.zeros(len(idx), np.int8)
    for k in range(len(idx)):
        i = idx[k]; e = ext[k]; a = atr[i]
        tp = e + side * 0.3 * a; sl = e - side * 0.1 * a
        for j in range(i + 1, min(end[k], i + 120) + 1):
            if side == 1:
                if L[j] <= sl: break
                if H[j] >= tp: y[k] = 1; break
            else:
                if H[j] >= sl: break
                if L[j] <= tp: y[k] = 1; break
    return y


def features(f, idx, side):
    C = f.C.to_numpy(); atr = f.atr.to_numpy(); cd = f.cd_g.to_numpy(); V = f.V.to_numpy()
    g = f.groupby("gday").agg(H=("H", "max"), L=("L", "min"))
    ph = f.gday.map(g.H.shift(1)).to_numpy(); pl = f.gday.map(g.L.shift(1)).to_numpy()
    lv = pd.read_parquet(os.path.join(P.CACHE, "levels.parquet"))
    poc = f.gday.map(lv.d_poc).to_numpy()
    dmin = f.groupby("gday").L.cummin().to_numpy(); dmax = f.groupby("gday").H.cummax().to_numpy()
    v5 = pd.Series(V).rolling(5).mean().to_numpy(); v60 = pd.Series(V).rolling(60).mean().to_numpy()
    X = pd.DataFrame({
        "zmena_CD_30m": (cd[idx] - cd[idx - 30]) * side,
        "zmena_ceny_30m_atr": (C[idx] - C[idx - 30]) / atr[idx] * side,
        "vzd_VWAP_SD": (C[idx] - f.vwap_d.to_numpy()[idx]) / f.sd_d.to_numpy()[idx] * side,
        "vzd_vcerejsi_extrem_atr": ((C[idx] - pl[idx]) if side == 1 else (ph[idx] - C[idx])) / atr[idx],
        "vzd_vcerejsi_POC_atr": (C[idx] - poc[idx]) / atr[idx] * side,
        "relativni_objem_5m": v5[idx] / v60[idx],
        "cas_min": f["mod"].to_numpy()[idx],
        "rozpeti_dne_atr": (dmax[idx] - dmin[idx]) / atr[idx],
        "CD_dne": cd[idx] * side,
        "vzd_W_VWAP_SD": (C[idx] - f.vwap_w.to_numpy()[idx]) / f.sd_w.to_numpy()[idx] * side,
    })
    return X


def main():
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    os.makedirs(OUT, exist_ok=True)
    f = P.load(); end, _ = day_end(f)
    H = f.H.to_numpy(); L = f.L.to_numpy(); C = f.C.to_numpy(); atr = f.atr.to_numpy()
    mod = f["mod"].to_numpy()
    win = (mod >= 585) & (mod <= 900)
    uni = []; trades = []; aucs = []
    for side, nm in ((1, "dno (novy 60min low) -> long"), (-1, "vrchol (novy 60min high) -> short")):
        if side == 1:
            prior = pd.Series(L).rolling(60).min().shift(1).to_numpy(); m = (L < prior) & win; ext = L
        else:
            prior = pd.Series(H).rolling(60).max().shift(1).to_numpy(); m = (H > prior) & win; ext = H
        idx = np.flatnonzero(m)
        idx = idx[(idx > 60)]
        # one event per 30 minutes at most (the first new extreme)
        keep = np.r_[True, np.diff(idx) > 30]; idx = idx[keep]
        y = label(H, L, ext[idx], side, atr, idx, end[idx])
        X = features(f, idx, side)
        base = y.mean()
        for c in X.columns:
            q = pd.qcut(X[c].rank(method="first"), 5, labels=False)
            r = pd.Series(y).groupby(q.to_numpy()).mean()
            uni.append(dict(udalost=nm, priznak=c, zakladni_podil=base,
                            **{f"kvintil_{k + 1}": r.get(k, np.nan) for k in range(5)},
                            rozdil_Q5_Q1=r.get(4, np.nan) - r.get(0, np.nan)))
        yr = f.ts.dt.year.to_numpy()[idx]
        pred = np.full(len(idx), np.nan)
        for ty in range(2015, 2027):
            tr = yr < ty; te = yr == ty
            if te.sum() < 50:
                continue
            mdl = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=100,
                                     subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
            mdl.fit(X[tr], y[tr]); pred[te] = mdl.predict_proba(X[te])[:, 1]
            aucs.append(dict(udalost=nm, rok=ty, auc=roc_auc_score(y[te], pred[te]), podil_obratu=y[te].mean()))
        ok = np.isfinite(pred)
        thr = pd.Series(pred[ok]).groupby(yr[ok]).transform(lambda s: s.quantile(0.9)).to_numpy()
        sel_all = idx[ok]; sel_top = idx[ok][pred[ok] >= thr]
        for lab, sel in (("vsechny udalosti 2015-26", sel_all), ("top 10 % modelu 2015-26", sel_top)):
            e = ext[sel]
            r = summarize(f"{nm} | {lab}", f, sel, np.full(len(sel), side), e + side * 0.3 * atr[sel],
                          e - side * 0.1 * atr[sel], np.minimum(end[sel], sel + 120))
            if r:
                trades.append(r)
    U = pd.DataFrame(uni); U.round(4).to_csv(os.path.join(OUT, "B_obraty_priznaky.csv"), index=False)
    A = pd.DataFrame(aucs); A.round(4).to_csv(os.path.join(OUT, "C_obraty_ml_auc.csv"), index=False)
    T = pd.DataFrame(trades); T.round(4).to_csv(os.path.join(OUT, "D_obraty_obchody.csv"), index=False)
    pd.set_option("display.width", 250)
    print(U.round(3).to_string()); print(A.groupby("udalost").auc.describe().round(3))
    print(T[["test", "n", "win_uzavrene", "nahodna_win", "hrube_b", "cisty_b", "t", "cisty_2011_18", "cisty_2019_26"]].round(3).to_string())


if __name__ == "__main__":
    main()
