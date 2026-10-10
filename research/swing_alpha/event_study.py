"""SWING ALPHA Experiment A: event study of every SW01-SW04 / H / benchmark signal.

Entry at the RTH open of day t+1 (nO_t), exit at the RTH close of day t+h.
R_h = side * (C_{t+h} - nO_t) / ATR14_t ; MFE / MAE over the bars t+1 .. t+h (in ATR).
Excess = R_h minus the same-side unconditional mean R_h of the same calendar year (removes drift).
Periods: DISC 2009-2018, VAL 2019-2022, OOS 2023-2026. t-stats use non-overlapping events
(greedy: next event only after the previous holding period ended). Block bootstrap (blocks of
consecutive non-overlapping events) gives a CI for the full-sample excess.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from signals import table, build_signals, markov, semi_markov  # noqa: E402

OUT = os.path.join(HERE, "out")
HS = (1, 2, 3, 5, 7, 10, 20)
START = "2009-03-01"


def period(idx):
    y = idx.year
    return np.where(y <= 2018, "DISC", np.where(y <= 2022, "VAL", "OOS"))


def forward(T):
    C, H, L, nO, A = (T[k].to_numpy() for k in ("C", "H", "L", "nO", "ATR"))
    n = len(T)
    R = {}; MFE = {}; MAE = {}
    for h in HS:
        r = np.full(n, np.nan); up = np.full(n, np.nan); dn = np.full(n, np.nan)
        ok = np.arange(n) + h < n
        r[ok] = (C[np.arange(n)[ok] + h] - nO[ok]) / A[ok]
        hh = pd.Series(H[::-1]).rolling(h, min_periods=h).max().to_numpy()[::-1]   # max H over t..t+h-1
        ll = pd.Series(L[::-1]).rolling(h, min_periods=h).min().to_numpy()[::-1]
        hh = np.r_[hh[1:], np.nan]; ll = np.r_[ll[1:], np.nan]                    # -> t+1..t+h
        up[ok] = (hh[ok] - nO[ok]) / A[ok]; dn[ok] = (ll[ok] - nO[ok]) / A[ok]
        R[h], MFE[h], MAE[h] = r, up, dn
    return R, MFE, MAE


def nonoverlap(idx, h):
    out = []; busy = -1
    for i in idx:
        if i > busy:
            out.append(i); busy = i + h
    return np.array(out, int)


def tstat(x):
    x = x[np.isfinite(x)]
    if len(x) < 5 or x.std() == 0:
        return np.nan
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x))


def block_boot(x, b=5, B=2000, seed=0):
    x = x[np.isfinite(x)]
    if len(x) < 2 * b:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(x) / b))
    st = rng.integers(0, len(x) - b + 1, size=(B, nb))
    means = np.array([np.concatenate([x[s:s + b] for s in row])[:len(x)].mean() for row in st])
    return np.percentile(means, 2.5), np.percentile(means, 97.5), (means <= 0).mean()


def bh(p, q=0.10):
    p = np.asarray(p, float); m = np.isfinite(p).sum()
    order = np.argsort(np.where(np.isfinite(p), p, 9))
    ok = np.zeros(len(p), bool)
    thr = 0
    for k, i in enumerate(order[:m], 1):
        if p[i] <= q * k / m:
            thr = k
    ok[order[:thr]] = True
    return ok


def main():
    from scipy.stats import norm
    T = table()
    S = build_signals(T)
    R, MFE, MAE = forward(T)
    valid = (T.index >= START) & T.ATR.notna().to_numpy() & T.nO.notna().to_numpy()
    per = period(T.index)
    yr = T.year.to_numpy()
    # same-year unconditional mean R_h (long side)
    drift = {h: pd.Series(R[h][valid]).groupby(yr[valid]).mean() for h in HS}
    rows = []
    for fam, name, side, m in S:
        m = m & valid
        idx = np.flatnonzero(m)
        for h in HS:
            r = R[h][idx]; ok = np.isfinite(r)
            ii = idx[ok]; r = side * r[ok]
            ex = r - side * drift[h].reindex(yr[ii]).to_numpy()
            mfe = (MFE[h][ii] if side > 0 else -MAE[h][ii]); mae = (MAE[h][ii] if side > 0 else -MFE[h][ii])
            row = dict(family=fam, signal=name, side="long" if side > 0 else "short", h=h, n=len(ii),
                       freq=len(ii) / max(valid.sum(), 1), R=r.mean() if len(r) else np.nan, excess=ex.mean() if len(r) else np.nan,
                       win=(r > 0).mean() if len(r) else np.nan, MFE=mfe.mean() if len(r) else np.nan, MAE=mae.mean() if len(r) else np.nan)
            pos = {j: k for k, j in enumerate(ii)}
            no = nonoverlap(ii, h)
            exn = ex[[pos[j] for j in no]] if len(no) else np.array([])
            row["n_no"] = len(no)
            row["t"] = tstat(exn)
            row["p"] = 2 * (1 - norm.cdf(abs(row["t"]))) if np.isfinite(row["t"]) else np.nan
            for P in ("DISC", "VAL", "OOS"):
                sel = per[ii] == P
                row[f"n_{P}"] = int(sel.sum())
                row[f"ex_{P}"] = ex[sel].mean() if sel.any() else np.nan
                row[f"R_{P}"] = r[sel].mean() if sel.any() else np.nan
                seln = per[no] == P if len(no) else np.array([], bool)
                row[f"t_{P}"] = tstat(exn[seln]) if len(no) else np.nan
            if h in (5, 10):
                lo, hi, pb = block_boot(exn)
                row["ci_lo"], row["ci_hi"], row["p_boot"] = lo, hi, pb
            rows.append(row)
    E = pd.DataFrame(rows)
    E["robust"] = ((E.t_DISC >= 2) & (E.ex_VAL > 0) & (E.ex_OOS > 0) & (E.n_VAL >= 20) & (E.n_OOS >= 20) & (E.ex_DISC > 0))
    E["fdr"] = False
    for h in HS:
        s = E.h == h
        E.loc[s, "fdr"] = bh(E.loc[s, "p"].to_numpy())
    os.makedirs(OUT, exist_ok=True)
    E.to_csv(os.path.join(OUT, "event_study.csv"), index=False)

    # regime statistics (SW04)
    Pm = markov(T)
    sm, runs = semi_markov(T)
    Pm.to_csv(os.path.join(OUT, "markov.csv"))
    sm.to_csv(os.path.join(OUT, "semi_markov.csv"), index=False)
    rs = runs.groupby("regime").len.describe()
    rs.to_csv(os.path.join(OUT, "regime_runs.csv"))
    share = pd.Series(T.regime[valid]).value_counts(normalize=True)
    share.to_csv(os.path.join(OUT, "regime_share.csv"))
    # stability of the transition matrix across periods
    for P in ("DISC", "VAL", "OOS"):
        markov(T, (per == P) & valid).to_csv(os.path.join(OUT, f"markov_{P}.csv"))
    # unconditional drift table
    pd.DataFrame({h: drift[h] for h in HS}).to_csv(os.path.join(OUT, "drift.csv"))

    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400); pd.set_option("display.max_colwidth", 48)
    c = ["family", "signal", "side", "h", "n", "R", "excess", "win", "t", "ex_DISC", "ex_VAL", "ex_OOS", "t_DISC", "robust", "fdr"]
    print(E[E.h == 5][c].round(3).to_string())
    print("robust any h:", E[E.robust].groupby(["family", "signal", "side"]).h.apply(list).to_string())
    print(Pm.round(3)); print(rs.round(1)); print(share.round(3))


if __name__ == "__main__":
    main()
