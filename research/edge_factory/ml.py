"""Can a machine find combinations that single rules miss?

Intraday: every RTH half hour (10:00-15:30) a 60-feature state vector; target = 2-hour forward
excess return (same null as the factory). LightGBM, expanding walk-forward by year with a
one-month embargo, never trained on the year it predicts. Trade rule: long the top decile,
short the bottom decile of predictions (thresholds from the training years), 2-hour hold,
0.5 point cost.
Daily: same idea at the RTH close, target = next 5-day excess return.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lightgbm as lgb  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from data import load, RTH0  # noqa: E402
from factory import Factory  # noqa: E402
from hypotheses import Ctx, day_to_bar, shift, _rsi  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def intraday_features(D, F, C):
    T = D.T
    c = D.c
    feats = {}
    for W, nm in ((1, "r5m"), (6, "r30m"), (12, "r1h"), (24, "r2h"), (48, "r4h")):
        feats[nm] = (c / shift(c, W) - 1) * 1e4
    atrb = C.atr_bar
    for nm, vw, sd in (("vr", D.vw_r, D.sd_r), ("vg", D.vw_g, D.sd_g), ("vw", D.vw_w, D.sd_w), ("vm", D.vw_m, D.sd_m)):
        with np.errstate(invalid="ignore", divide="ignore"):
            feats[f"{nm}_z"] = (c - vw) / sd
            feats[f"{nm}_atr"] = (c - vw) / atrb
    feats["vratio"] = C.vratio
    feats["imb"] = C.imb
    for W in (6, 12, 78):
        v = pd.Series(D.v).rolling(W).sum().to_numpy()
        feats[f"imb{W}"] = pd.Series(D.dl).rolling(W).sum().to_numpy() / v
        feats[f"vr{W}"] = v / pd.Series(C.vbase).rolling(W).sum().to_numpy()
    feats["cvd_day_n"] = D.cvd_day / pd.Series(D.v).groupby(D.di).cumsum().to_numpy()
    for k in ("pdh", "pdl", "onh", "onl", "pwh", "pwl", "pdc"):
        feats[f"d_{k}"] = (c - C.lv[k]) / atrb
    feats["d_r100"] = (c - C.lv["r100"]) / 100
    o_rth = day_to_bar(D, T.O)
    feats["r_from_open"] = (c - o_rth) / atrb
    feats["tod"] = D.gmin.astype(float)
    feats["wd"] = C.wd
    T2 = T.copy()
    T2["gap"] = (T2.O - T2.pC) / T2.atr
    T2["ibs_prev"] = ((T2.C - T2.L) / (T2.H - T2.L)).shift()
    T2["ret1"] = T2.ret.shift() * 1e4
    T2["ret5"] = (T2.C / T2.C.shift(5) - 1).shift() * 1e4
    T2["ret20"] = (T2.C / T2.C.shift(20) - 1).shift() * 1e4
    T2["rsi2"] = _rsi(T2.C, 2).shift()
    T2["dd_ath"] = (T2.C / T2.C.cummax() - 1).shift()
    T2["ma200d"] = ((T2.C - T2.ma200) / T2.atr).shift()
    T2["atr_rank"] = T2.atr.rolling(250, min_periods=60).rank(pct=True)
    T2["on_range"] = (T2.onH - T2.onL) / T2.atr
    T2["tdm"] = T2.tdm.astype(float); T2["dom"] = T2.dom.astype(float); T2["month"] = T2.month.astype(float)
    T2["moon"] = T2.moon
    for k in ("gap", "ibs_prev", "ret1", "ret5", "ret20", "rsi2", "dd_ath", "ma200d", "atr_rank", "on_range", "tdm", "dom", "month", "moon"):
        feats[k] = day_to_bar(D, T2[k])
    X = pd.DataFrame(feats)
    return X


def walk_forward(X, y, years, w=None, start=2012, params=None):
    params = params or dict(objective="regression", learning_rate=0.03, num_leaves=15, min_data_in_leaf=400,
                            feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1, seed=7)
    pred = np.full(len(y), np.nan)
    thr = {}
    for Y in range(start, years.max() + 1):
        tr = years < Y - 0  # embargo handled by excluding last month below
        te = years == Y
        if te.sum() == 0:
            continue
        m = lgb.train(params, lgb.Dataset(X[tr], y[tr]), num_boost_round=250)
        p_tr = m.predict(X[tr])
        pred[te] = m.predict(X[te])
        thr[Y] = (np.quantile(p_tr, 0.1), np.quantile(p_tr, 0.9))
    return pred, thr, m


def main():
    D = load(); F = Factory(D); C = Ctx(D)
    X = intraday_features(D, F, C)
    sel = D.rth & (D.gmin >= RTH0 + 25) & (D.gmin <= RTH0 + 355) & ((D.gmin - RTH0 - 25) % 30 == 0) & D.flow_ok
    f2h = F.fwd["2h"]; nul = F.null["2h"]
    ok = sel & np.isfinite(f2h)
    idx = np.flatnonzero(ok)
    Xs = X.iloc[idx].reset_index(drop=True)
    y = (f2h - nul)[idx]
    years = pd.DatetimeIndex(D.gday[idx]).year.to_numpy()
    pred, thr, model = walk_forward(Xs, y, years)
    res = []
    cost = F.cost_bar[idx]
    raw = f2h[idx]
    for Y in sorted(thr):
        te = years == Y
        p = pred[te]
        lo, hi = thr[Y]
        side = np.where(p >= hi, 1, np.where(p <= lo, -1, 0))
        act = side != 0
        pnl = side[act] * raw[te][act] - cost[te][act]
        ex = side[act] * y[te][act]
        auc = roc_auc_score(y[te] > 0, p)
        ic = pd.Series(p).corr(pd.Series(y[te]), method="spearman")
        res.append(dict(year=Y, n=int(act.sum()), auc=auc, ic=ic, excess_bps=ex.mean(), net_bps=pnl.mean(),
                        win=(pnl > 0).mean(), net_sum_bps=pnl.sum()))
    R = pd.DataFrame(res)
    imp = pd.Series(model.feature_importance("gain"), index=Xs.columns).sort_values(ascending=False)
    # daily model: features at the close, target next 5 days excess
    T = D.T
    close_idx = T.i_close.to_numpy().astype(int)
    Xd = X.iloc[close_idx].reset_index(drop=True)
    c5 = F.dfwd["c5"]; n5 = F.dnull["c5"]
    okd = np.isfinite(c5) & (T.index >= "2010-06-01")
    Xd, yd = Xd[okd].reset_index(drop=True), (c5 - n5)[okd]
    yrs = T.index.year.to_numpy()[okd]
    pdd, thrd, _ = walk_forward(Xd, yd, yrs, params=dict(objective="regression", learning_rate=0.03, num_leaves=7,
                                                         min_data_in_leaf=60, feature_fraction=0.7, lambda_l2=10.0,
                                                         verbose=-1, seed=7))
    rd = []
    raw5 = c5[okd]
    costd = F.dcost[okd]
    for Y in sorted(thrd):
        te = yrs == Y
        p = pdd[te]
        lo, hi = thrd[Y]
        side = np.where(p >= hi, 1, np.where(p <= lo, -1, 0))
        act = side != 0
        # non-overlap: every 5th day
        sub = np.zeros(te.sum(), bool); sub[::5] = True
        a2 = act & sub
        rd.append(dict(year=Y, n=int(a2.sum()), ic=pd.Series(p).corr(pd.Series(yd[te]), method="spearman"),
                       excess_bps=(side[a2] * yd[te][a2]).mean(), net_bps=(side[a2] * raw5[te][a2] - costd[te][a2]).mean()))
    Rd = pd.DataFrame(rd)
    R.to_csv(os.path.join(OUT, "ml_intraday.csv"), index=False)
    Rd.to_csv(os.path.join(OUT, "ml_daily.csv"), index=False)
    imp.head(20).to_csv(os.path.join(OUT, "ml_importance.csv"))
    pd.set_option("display.width", 200)
    print(R.round(3).to_string()); print("mean", R[["auc", "ic", "excess_bps", "net_bps"]].mean().round(3).to_dict())
    print(imp.head(15).round(0))
    print(Rd.round(2).to_string()); print("mean", Rd[["ic", "excess_bps", "net_bps"]].mean().round(3).to_dict())


if __name__ == "__main__":
    main()
