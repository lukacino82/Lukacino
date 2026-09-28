"""
Historical correction database + analog / hazard model (blueprint B06, B07, H).

Every decision day is one observation row. Features are causal; future MAE/MFE and
target-before-stop are labels only. Two independent estimators of P(TP before SL):

  * logistic regression (L2, standardised, expanding walk-forward with purge+embargo)
  * k-NN analog engine over the same feature space (training window only)

The model is only allowed to trade when its probability exceeds the break-even probability of
the exit profile plus a cost margin, so a "good looking" correction that is not priced well is
skipped. Calibration is reported (Brier score, decile reliability), not just P&L.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lab import Lab
from sieve import RES

FEATURES = [
    "dd", "ddq", "days_from_peak", "days_from_low", "recovery_frac", "dd_velocity", "dd_atr",
    "downdays", "wstreak3", "wstreak5", "cumret2", "cumret5", "cumret10",
    "cumret5_pct", "cumret10_pct", "atr_shock", "atr_shock2", "gap_atr", "rth_move_atr",
    "ibs", "down_effort", "atr_ratio", "vol_z", "rsi2", "rsi14", "bb_pctb",
    "dist200_atr", "dist_wvwap_atr", "dist_mvwap_atr", "dist_avwap_atr", "time_under_water",
    "delta_z", "price_response", "cd5", "hi20_dd_atr", "hi50_dd_atr",
]
EMBARGO = 25          # >= max holding period, in sessions


def labels(d: pd.DataFrame, tp_atr=1.0, sl_atr=1.0, horizon=20):
    """target-before-stop on daily bars; if both are touched the same day, count the stop (SL first)."""
    c, h, l, atr = d.close.values, d.high.values, d.low.values, d.atr20.values
    n = len(d)
    y = np.full(n, np.nan)
    mfe = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    for i in range(n - 1):
        if not np.isfinite(atr[i]):
            continue
        ep = c[i]
        tp, sl = ep + tp_atr * atr[i], ep - sl_atr * atr[i]
        hi, lo = -np.inf, np.inf
        res = 0.0
        for j in range(i + 1, min(i + 1 + horizon, n)):
            hi, lo = max(hi, h[j]), min(lo, l[j])
            if l[j] <= sl:
                res = 0.0
                break
            if h[j] >= tp:
                res = 1.0
                break
        else:
            res = 1.0 if c[min(i + horizon, n - 1)] > ep else 0.0
        y[i] = res
        mfe[i] = (hi - ep) / atr[i]
        mae[i] = (ep - lo) / atr[i]
    return y, mfe, mae


def _fit_logit(X, y, l2=10.0, iters=30):
    """L2 logistic regression by Newton-Raphson (IRLS) - no sklearn dependency"""
    Xb = np.c_[np.ones(len(X)), X]
    w = np.zeros(Xb.shape[1])
    R = l2 * np.eye(Xb.shape[1])
    R[0, 0] = 0.0                                   # do not penalise the intercept
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Xb @ w, -30, 30)))
        g = Xb.T @ (y - p) - R @ w
        H = Xb.T @ (Xb * (p * (1 - p))[:, None]) + R
        step = np.linalg.solve(H + 1e-6 * np.eye(len(w)), g)
        w += step
        if np.abs(step).max() < 1e-6:
            break
    return w


def _predict(w, X):
    return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


def knn_prob(Xtr, ytr, Xte, k=50):
    """analog engine: empirical hit rate of the k nearest past corrections"""
    out = np.empty(len(Xte))
    for i in range(len(Xte)):
        dist = ((Xtr - Xte[i]) ** 2).sum(1)
        idx = np.argpartition(dist, min(k, len(dist) - 1))[:k]
        out[i] = ytr[idx].mean()
    return out


def build(lab: Lab, tp_atr=1.0, sl_atr=1.0, in_correction=True):
    d = lab.d
    y, mfe, mae = labels(d, tp_atr, sl_atr)
    X = d[FEATURES].replace([np.inf, -np.inf], np.nan)
    ok = X.notna().all(1).values & np.isfinite(y)
    if in_correction:                                    # only decision days inside a correction
        ok &= (d.dd < -0.01).values
    return X.values, y, mfe, mae, ok


def walk_forward(lab: Lab, tp_atr=1.0, sl_atr=1.0, first_year=2013, k=50):
    d = lab.d
    X, y, mfe, mae, ok = build(lab, tp_atr, sl_atr)
    years = d.index.year.values
    p_lr = np.full(len(d), np.nan)
    p_nn = np.full(len(d), np.nan)
    for Y in range(first_year, years.max() + 1):
        te = ok & (years == Y)
        tr = ok & (years < Y)
        # purge + embargo: drop training rows whose label window can reach into the test year
        cut = np.argmax(years == Y)
        tr &= np.arange(len(d)) < max(cut - EMBARGO, 0)
        if tr.sum() < 200 or te.sum() == 0:
            continue
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
        w = _fit_logit(Xtr, y[tr])
        p_lr[te] = _predict(w, Xte)
        p_nn[te] = knn_prob(Xtr, y[tr], Xte, k)
    return p_lr, p_nn, y, mfe, mae, ok


def auc(p, y):
    """rank-based AUC: probability that a winner is scored above a loser"""
    o = np.argsort(p)
    r = np.empty(len(p))
    r[o] = np.arange(1, len(p) + 1)
    n1, n0 = y.sum(), (1 - y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def calibration(p, y, mask, bins=10):
    m = mask & np.isfinite(p)
    if m.sum() < 50:
        return {}
    q = pd.qcut(pd.Series(p[m]), bins, duplicates="drop", labels=False)
    df = pd.DataFrame({"p": p[m], "y": y[m], "q": q}).groupby("q").agg(n=("y", "size"), pred=("p", "mean"), real=("y", "mean"))
    return dict(brier=float(((p[m] - y[m]) ** 2).mean()), base=float(y[m].mean()),
                auc=round(auc(p[m], y[m]), 3),
                top_decile=float(df.real.iloc[-1]), bottom_decile=float(df.real.iloc[0]),
                deciles=df.round(3).to_dict("index"))


def main():
    lab = Lab()
    res = {}
    for tp, sl in ((1.0, 1.0), (1.5, 1.0), (1.0, 1.5)):
        p_lr, p_nn, y, mfe, mae, ok = walk_forward(lab, tp, sl)
        be = sl / (tp + sl)                                   # break-even hit rate of this RRR
        r = dict(tp_atr=tp, sl_atr=sl, breakeven=round(be, 3),
                 lr=calibration(p_lr, y, ok), knn=calibration(p_nn, y, ok))
        res[f"tp{tp}_sl{sl}"] = r
        np.save(RES / f"corrmodel_plr_{tp}_{sl}.npy", p_lr)
        np.save(RES / f"corrmodel_pnn_{tp}_{sl}.npy", p_nn)
        print(f"TP{tp}/SL{sl} breakeven {be:.3f} base {r['lr'].get('base'):.3f} | "
              f"LR brier {r['lr'].get('brier'):.3f} auc {r['lr'].get('auc')} top/bot "
              f"{r['lr'].get('top_decile'):.3f}/{r['lr'].get('bottom_decile'):.3f} | "
              f"kNN brier {r['knn'].get('brier'):.3f} auc {r['knn'].get('auc')} top/bot "
              f"{r['knn'].get('top_decile'):.3f}/{r['knn'].get('bottom_decile'):.3f}")
        for name, p in (("LR", p_lr), ("kNN", p_nn)):
            m = ok & np.isfinite(p)
            hi = m & (p > be + 0.05)
            print(f"   {name}: signals {hi.sum()}, realised hit {y[hi].mean():.3f} vs breakeven {be:.3f}, "
                  f"mean MFE {mfe[hi].mean():.2f} MAE {mae[hi].mean():.2f}")
    json.dump(res, open(RES / "correction_model.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
