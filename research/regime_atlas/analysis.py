"""Regime Atlas analysis: when did each strategy beat ES buy & hold, and in which market conditions.

Market conditions are described two ways:
  * per day   - phase by drawdown from the all-time high, trailing 63-day trend, 20-day volatility;
  * per quarter - a label from the quarter's own path (return, max drawdown, volatility, efficiency).
Two comparisons with B&H:
  * raw excess  = strategy return - B&H return (what the account shows);
  * alpha       = strategy return - beta x B&H return (beta from the full sample), i.e. the part that is
                  not just more or less ES exposure.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


def comp(x):
    return (1 + x.fillna(0)).prod() - 1


def day_regimes(T, idx):
    px = T.gC.reindex(idx)
    dd = px / px.cummax() - 1
    phase = pd.cut(dd, [-1, -0.20, -0.10, -0.05, 1], labels=["Medvědí trh (DD ≥ 20 %)", "Korekce (DD 10–20 %)", "Pullback (DD 5–10 %)", "U maxim (DD < 5 %)"])
    r63 = px / px.shift(63) - 1
    eff = (px - px.shift(63)).abs() / px.diff().abs().rolling(63).sum()
    trend = np.select([r63 > 0.08, r63 > 0.02, (r63 > -0.02) | (eff < 0.1), r63 > -0.08], ["Silný růst", "Mírný růst", "Stranově", "Mírný pokles"], "Silný pokles")
    vol = T.rv20.reindex(idx)
    volr = pd.cut(vol, [0, 0.12, 0.20, 0.30, 9], labels=["Nízká vol (< 12 %)", "Normální vol (12–20 %)", "Vysoká vol (20–30 %)", "Krizová vol (> 30 %)"])
    return pd.DataFrame({"phase": phase.astype(str), "trend": trend, "vol": volr.astype(str), "dd": dd}, index=idx)


def quarter_table(bh, T):
    px = T.gC
    rows = []
    for q, x in bh.groupby(bh.index.to_period("Q")):
        eq = (1 + x).cumprod()
        mdd = (eq / eq.cummax() - 1).min()
        p = px.reindex(x.index)
        eff = abs(p.iloc[-1] - p.iloc[0]) / p.diff().abs().sum() if len(p) > 2 else np.nan
        rows.append(dict(q=str(q), ret=comp(x), mdd=mdd, vol=x.std() * np.sqrt(252), eff=eff,
                         big=(x.abs() > 0.02).sum(), ath_dd=(px.reindex(x.index) / px.cummax().reindex(x.index) - 1).min()))
    Q = pd.DataFrame(rows).set_index("q")
    lab = []
    for _, r in Q.iterrows():
        if r.mdd <= -0.15 or r.vol > 0.35:
            l = "Krach / panika"
        elif r.ret < -0.05:
            l = "Pokles"
        elif r.mdd <= -0.07 and r.ret > 0:
            l = "Korekce s návratem (V)"
        elif r.mdd <= -0.07:
            l = "Korekce"
        elif r.ret > 0.07 and r.eff > 0.2:
            l = "Strmý trend nahoru"
        elif r.ret > 0.02:
            l = "Trend nahoru"
        else:
            l = "Stranový pohyb"
        lab.append(l)
    Q["label"] = lab
    return Q


def main():
    import sys
    sys.path.insert(0, HERE)
    from strategies import build, META
    R, T = build()
    bh = R["B&H"]
    names = [c for c in R.columns if c != "B&H"]
    # full-sample beta of each strategy to B&H
    beta = {c: (R[c].cov(bh) / bh.var()) if R[c].notna().sum() > 100 else np.nan for c in names}
    DR = day_regimes(T, R.index)
    Q = quarter_table(bh, T)
    # per quarter excess and alpha
    qx, qa = {}, {}
    for c in names:
        x = R[c]
        g = pd.DataFrame({"s": x, "b": bh}).groupby(R.index.to_period("Q"))
        rs = g.s.apply(lambda v: comp(v) if v.notna().sum() > 20 else np.nan)
        rb = g.b.apply(comp)
        qx[c] = rs - rb
        qa[c] = rs - beta[c] * rb
    QX = pd.DataFrame(qx); QA = pd.DataFrame(qa)
    QX.index = QX.index.astype(str); QA.index = QA.index.astype(str)
    # per year
    yx = {}
    for c in names:
        g = pd.DataFrame({"s": R[c], "b": bh}).groupby(R.index.year)
        yx[c] = g.s.apply(lambda v: comp(v) if v.notna().sum() > 100 else np.nan) - g.b.apply(comp)
    YX = pd.DataFrame(yx)
    yb = bh.groupby(R.index.year).apply(comp)
    # by quarter label
    lab_rows = []
    for c in names:
        for l, idx in Q.groupby("label").groups.items():
            ex = QX.loc[QX.index.isin(idx), c].dropna(); al = QA.loc[QA.index.isin(idx), c].dropna()
            if len(ex) == 0:
                continue
            lab_rows.append(dict(strategy=c, label=l, n=len(ex), excess=ex.mean(), beat=(ex > 0).mean(), alpha=al.mean()))
    LB = pd.DataFrame(lab_rows)
    # by day regime: annualised mean daily excess and alpha
    reg_rows = []
    for c in names:
        x = R[c]
        for dim in ("phase", "trend", "vol"):
            for l, idx in DR.groupby(dim).groups.items():
                if l in ("nan", "None"):
                    continue
                xs = x.reindex(idx).dropna(); bs = bh.reindex(xs.index)
                if len(xs) < 40:
                    continue
                reg_rows.append(dict(strategy=c, dim=dim, regime=l, days=len(xs), excess=(xs - bs).mean() * 252,
                                     alpha=(xs - beta[c] * bs).mean() * 252, strat=xs.mean() * 252, bh=bs.mean() * 252))
    RG = pd.DataFrame(reg_rows)
    # drivers: regress quarterly alpha on standardised quarter features
    F = Q[["ret", "vol", "eff", "mdd"]].copy()
    Fz = (F - F.mean()) / F.std()
    drv = []
    for c in names:
        y = QA[c].reindex(Fz.index).dropna()
        if len(y) < 12:
            continue
        X = np.c_[np.ones(len(y)), Fz.loc[y.index].to_numpy()]
        b, *_ = np.linalg.lstsq(X, y.to_numpy(), rcond=None)
        res = y.to_numpy() - X @ b
        r2 = 1 - res.var() / y.to_numpy().var()
        drv.append(dict(strategy=c, b_ret=b[1], b_vol=b[2], b_eff=b[3], b_mdd=b[4], r2=r2))
    DV = pd.DataFrame(drv)
    # rolling 2-year alpha (annualised) - life cycle of each edge
    roll = {}
    for c in names:
        a = R[c] - beta[c] * bh
        roll[c] = a.rolling(504, min_periods=400).mean() * 252
    RO = pd.DataFrame(roll).resample("ME").last()
    # overall summary
    summ = []
    for c in names:
        x = R[c].dropna(); b = bh.reindex(x.index)
        yrs = len(x) / 252
        eq = (1 + x).cumprod()
        summ.append(dict(strategy=c, family=META[c][0], mechanism=META[c][1], rule=META[c][2], start=str(x.index[0].date()),
                         cagr=eq.iloc[-1] ** (1 / yrs) - 1, bh_cagr=(1 + b).prod() ** (1 / yrs) - 1,
                         vol=x.std() * np.sqrt(252), sharpe=x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan,
                         bh_sharpe=b.mean() / b.std() * np.sqrt(252), mdd=(eq / eq.cummax() - 1).min(),
                         beta=beta[c], alpha=(x - beta[c] * b).mean() * 252,
                         t_alpha=(x - beta[c] * b).mean() / (x - beta[c] * b).std() * np.sqrt(len(x)),
                         q_beat=(QX[c].dropna() > 0).mean(), q_alpha_pos=(QA[c].dropna() > 0).mean(),
                         y_beat=(YX[c].dropna() > 0).mean()))
    SM = pd.DataFrame(summ)
    # B&H scaled to the same volatility: does the strategy beat B&H at equal risk?
    SM["bh_samevol_cagr"] = [((1 + bh.reindex(R[c].dropna().index) * (R[c].std() / bh.std())).prod()) ** (252 / R[c].notna().sum()) - 1 for c in names]
    for name, df in (("summary", SM), ("quarters", Q.reset_index()), ("q_excess", QX.reset_index()), ("q_alpha", QA.reset_index()),
                     ("y_excess", YX.reset_index()), ("by_label", LB), ("by_regime", RG), ("drivers", DV)):
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    RO.to_csv(os.path.join(OUT, "rolling_alpha.csv"))
    yb.to_csv(os.path.join(OUT, "bh_years.csv"))
    DR.to_csv(os.path.join(OUT, "day_regimes.csv"))
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(SM.drop(columns=["mechanism", "rule"]).round(3).to_string())
    print(Q.round(3).to_string())
    print(Q.label.value_counts())


if __name__ == "__main__":
    main()
