"""Strategies built from the effects that survived the mega scan, against buy & hold (long ES, daily decision at the close).

Exposure L_t (contracts' notional / equity) is set at the close of day t for the next close-to-close day.
Cost: 0.5 point per contract traded on every change of exposure. Return of day t+1 = L_t x (dC_{t+1} / cash_t).
Rules (fixed in advance, no fitting):   R1 RSI(2) < 10 -> 2x      R2 >= 3 lower closes -> 2x until the first higher close
  R3 week-to-date drop in the lowest decile -> 2x                 R4 any of R1-R3 -> 2x        R5 R4 and overbought -> 0.5x
ML (walk-forward, refit every year on all earlier data, 147 ranked features, target = next-day move in ATR):
  ridge and LightGBM; exposure = clip(1 + z, 0, 2) where z = prediction / std of training predictions; and a
  long/flat version (1x when the prediction > 0, else 0).
Vol target: exposure scaled to 15 % annual volatility (20-day realised), cap 2x; and vol target x R4.
Reported: 2012-2026 (common window), split 2012-2020 / 2021-2026 (2021+ = holdout of the scan), CAGR when the whole
exposure is rescaled so that the maximum drawdown equals buy & hold's.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily as D

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
START = "2012-01-01"


def equity(L, r, cash, lmax=None):
    L = np.asarray(L, float)
    cost = np.abs(np.diff(np.r_[0.0, L])) * D.COST / cash
    ret = L * r - cost
    return ret


def metrics(ret, bh, idx):
    eq = np.cumprod(1 + ret); yrs = len(ret) / 252
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    X = np.c_[np.ones(len(bh)), bh]; b, *_ = np.linalg.lstsq(X, ret, rcond=None); res = ret - X @ b
    yr = pd.Series(ret, index=idx).groupby(idx.year).apply(lambda x: np.prod(1 + x) - 1)
    return dict(CAGR=eq[-1] ** (1 / yrs) - 1, vol=ret.std() * np.sqrt(252), Sharpe=ret.mean() / ret.std() * np.sqrt(252), maxDD=dd,
                alfa_rok=b[0] * 252, alfa_t=b[0] / np.sqrt(res.var() / len(ret)), beta=b[1], nejhorsi_rok=yr.min(),
                let_lepsich_nez_BH=int((yr > pd.Series(bh, index=idx).groupby(idx.year).apply(lambda x: np.prod(1 + x) - 1)).sum()))


def dd_matched(L, r, cash, target_dd):
    lo, hi = 0.05, 8.0
    for _ in range(40):
        c = (lo + hi) / 2
        ret = equity(L * c, r, cash); eq = np.cumprod(1 + np.maximum(ret, -0.99))
        dd = (eq / np.maximum.accumulate(eq) - 1).min()
        if dd < target_dd:
            hi = c
        else:
            lo = c
    ret = equity(L * lo, r, cash); eq = np.cumprod(1 + ret)
    return lo, eq[-1] ** (252 / len(ret)) - 1


def ml_predictions(F, y, idx):
    import lightgbm as lgb
    from sklearn.linear_model import Ridge
    R = F.rolling(252, min_periods=200).rank(pct=True).fillna(0.5).to_numpy() - 0.5
    ok = np.isfinite(y)
    P = {"ridge": np.full(len(y), np.nan), "lgbm": np.full(len(y), np.nan)}
    Z = {"ridge": np.full(len(y), np.nan), "lgbm": np.full(len(y), np.nan)}
    years = sorted(set(idx.year))
    for yv in years:
        if yv < 2012:
            continue
        tr = (idx.year < yv) & ok & (np.arange(len(y)) > 260); te = idx.year == yv
        tr[np.flatnonzero(idx.year < yv)[-2:]] = False                       # target of the last train rows is known
        for nm, mdl in (("ridge", Ridge(alpha=300.0)),
                        ("lgbm", lgb.LGBMRegressor(n_estimators=200, learning_rate=0.02, num_leaves=6, min_child_samples=60,
                                                   subsample=0.7, subsample_freq=1, colsample_bytree=0.5, reg_lambda=5, verbose=-1))):
            mdl.fit(R[tr], np.clip(y[tr], -3, 3))
            ptr = mdl.predict(R[tr]); p = mdl.predict(R[te])
            P[nm][te] = p; Z[nm][te] = (p - 0) / ptr.std()
    return P, Z


def main():
    o = D.build(); t = o["t"]; F = o["F"]
    idx = t.index
    cash = t.cash.to_numpy(); C = t.C.to_numpy(); A = t.atr.to_numpy()
    r_next = np.r_[np.diff(C), np.nan] / cash                    # return of the next day per unit exposure
    y_atr = np.r_[np.diff(C), np.nan] / A
    P, Z = ml_predictions(F, y_atr, idx)
    rsi2 = F.rsi2.to_numpy()
    r1 = t.C.diff().to_numpy()
    dn = pd.Series(r1 < 0, index=idx); streak = dn.groupby((~dn).cumsum()).cumsum().to_numpy()
    wtd_rank = F.wtd.rolling(252, min_periods=200).rank(pct=True).to_numpy()
    R1 = rsi2 < 10; R2 = streak >= 3; R3 = wtd_rank <= 0.10
    R4 = R1 | R2 | R3
    ob = (rsi2 > 95) & (F.dma200.to_numpy() > 0)
    pr = pd.Series(np.r_[np.nan, np.diff(C)] / np.r_[np.nan, cash[:-1]], index=idx)
    vol = pr.rolling(20).std().to_numpy() * np.sqrt(252)
    vt = np.clip(0.15 / vol, 0, 2.0)
    strat = {
        "Buy & hold 1x": np.ones(len(idx)),
        "R1: RSI(2)<10 -> 2x": np.where(R1, 2.0, 1.0),
        "R2: 3 nizsi close -> 2x": np.where(R2, 2.0, 1.0),
        "R3: tyden v nejhorsim decilu -> 2x": np.where(R3, 2.0, 1.0),
        "R4: jakakoli slabost -> 2x": np.where(R4, 2.0, 1.0),
        "R5: slabost 2x, prekoupenost 0.5x": np.where(R4, 2.0, np.where(ob, 0.5, 1.0)),
        "R6: jen slabost (jinak mimo trh)": np.where(R4, 1.0, 0.0),
        "R7: slabost 3x, jinak 1x": np.where(R4, 3.0, 1.0),
        "ML ridge: 1 + z (0..2)": np.clip(1 + Z["ridge"], 0, 2),
        "ML lgbm: 1 + z (0..2)": np.clip(1 + Z["lgbm"], 0, 2),
        "ML ridge: long/flat": np.where(P["ridge"] > 0, 1.0, 0.0),
        "ML lgbm: long/flat": np.where(P["lgbm"] > 0, 1.0, 0.0),
        "ML prumer: 1 + 1.5 z (0..3)": np.clip(1 + 1.5 * (Z["ridge"] + Z["lgbm"]) / 2, 0, 3),
        "Vol target 15 %": vt,
        "Vol target x R4": np.clip(vt * np.where(R4, 2.0, 1.0), 0, 3.0),
        "Vol target x ML prumer": np.clip(vt * np.clip(1 + (Z["ridge"] + Z["lgbm"]) / 2, 0, 2), 0, 3.0),
    }
    m = (idx >= START) & np.isfinite(r_next) & np.isfinite(Z["ridge"]) & np.isfinite(vt)
    rows = []; curves = {}
    bh_all = equity(strat["Buy & hold 1x"][m], r_next[m], cash[m])
    bh_dd = (np.cumprod(1 + bh_all) / np.maximum.accumulate(np.cumprod(1 + bh_all)) - 1).min()
    for nm, L in strat.items():
        ret = equity(L[m], r_next[m], cash[m]); curves[nm] = np.cumprod(1 + ret)
        row = dict(strategie=nm, prum_expozice=L[m].mean(), podil_dnu_v_trhu=(L[m] > 0).mean(), **metrics(ret, bh_all, idx[m]))
        c, cg = dd_matched(L[m], r_next[m], cash[m], bh_dd)
        row["nasobek_pro_stejny_DD"] = c; row["CAGR_pri_stejnem_DD"] = cg
        for lab, a, b in (("2012_20", "2012-01-01", "2021-01-01"), ("2021_26", "2021-01-01", "2030-01-01")):
            mm = (idx[m] >= a) & (idx[m] < b)
            x = metrics(ret[mm], bh_all[mm], idx[m][mm])
            row[f"CAGR_{lab}"] = x["CAGR"]; row[f"Sharpe_{lab}"] = x["Sharpe"]; row[f"maxDD_{lab}"] = x["maxDD"]; row[f"alfa_t_{lab}"] = x["alfa_t"]
        rows.append(row)
    T = pd.DataFrame(rows)
    T.round(4).to_csv(os.path.join(OUT, "strategie_vs_BH.csv"), index=False)
    pd.DataFrame(curves, index=idx[m]).to_parquet(os.path.join(OUT, "strategie_equity.parquet"))
    # prediction quality
    ic = {k: pd.Series(P[k][m]).corr(pd.Series(y_atr[m]), method="spearman") for k in P}
    icy = pd.DataFrame({k: pd.Series(P[k][m], index=idx[m]).groupby(idx[m].year).apply(
        lambda s: s.corr(pd.Series(y_atr[m], index=idx[m]).loc[s.index], method="spearman")) for k in P})
    icy.round(3).to_csv(os.path.join(OUT, "ml_ic_po_letech.csv"))
    pd.set_option("display.width", 280); pd.set_option("display.max_columns", 40)
    print("IC", ic); print(icy.round(3).T.to_string())
    print(T[["strategie", "prum_expozice", "CAGR", "vol", "Sharpe", "maxDD", "alfa_rok", "alfa_t", "CAGR_pri_stejnem_DD", "let_lepsich_nez_BH",
             "CAGR_2012_20", "CAGR_2021_26", "Sharpe_2012_20", "Sharpe_2021_26", "alfa_t_2012_20", "alfa_t_2021_26"]].round(3).to_string())


if __name__ == "__main__":
    main()
