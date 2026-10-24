"""Part E recomputed with true index returns: buy & hold from the US500Cash-equivalent series (bcl/bcl_data.py)
instead of the back-adjusted ES (additive adjustment understates percentage returns)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bcl"))
import analysis as A
import bcl_data as BD
import engine as E


def cash_daily():
    c = BD.load()[["ts", "C"]]
    c["gday"] = (c.ts + pd.Timedelta(hours=6)).dt.normalize()
    return c.groupby("gday").C.last()


def main():
    bars = E.load_bars()[["ts", "gday"]]
    px = cash_daily()
    bh = px.pct_change().dropna()
    old = pd.read_csv(os.path.join(A.OUT, "E_alpha.csv"))
    rows = []
    for _, o in old.iterrows():
        z = A.load(o["mode"], o.horizont, o.smer)
        i_sl = int(np.argmin(np.abs(z["slv"] - o.SL)))
        R, ex, win, loss, opn = A.outcomes(z, i_sl, o.RRR)
        M = A.meta(bars, z["ent"])
        order = np.argsort(z["ent"], kind="stable")
        ok = (M.ts >= A.SPLIT).to_numpy()[order]
        tk = A.sequence(z["ent"][order], ex[order], ok)
        idx = order[tk]
        eday = bars.gday.iloc[np.minimum(z["ent"][idx] + ex[idx], len(bars) - 1)].to_numpy()
        pr = pd.Series(0.01 * R[idx], index=eday).groupby(level=0).sum()
        b2 = bh.loc[A.SPLIT:]
        sr = pr.reindex(b2.index).fillna(0)
        X = np.c_[np.ones(len(b2)), b2.to_numpy()]
        coef, *_ = np.linalg.lstsq(X, sr.to_numpy(), rcond=None)
        res = sr.to_numpy() - X @ coef
        se = np.sqrt(res.var(ddof=2) / len(b2))
        yrs = len(sr) / 252
        eq = (1 + sr).cumprod(); beq = (1 + b2).cumprod()
        rows.append(dict(mode=o["mode"], horizont=o.horizont, smer=o.smer, SL=o.SL, RRR=o.RRR,
                         R_vyber_2011_18=o.R_vyber_2011_18, obchodu_2019_26=len(idx), R_2019_26=R[idx].mean(),
                         CAGR=eq.iloc[-1] ** (1 / yrs) - 1, maxDD=(eq / eq.cummax() - 1).min(),
                         alfa_rok=coef[0] * 252, alfa_t=coef[0] / se, beta=coef[1], BH_CAGR=beq.iloc[-1] ** (1 / yrs) - 1,
                         BH_maxDD=(beq / beq.cummax() - 1).min()))
    T = pd.DataFrame(rows); T.round(4).to_csv(os.path.join(A.OUT, "E_alpha.csv"), index=False)
    print(T.round(3).to_string())
    px.to_frame("C").to_parquet("/tmp/claude-0/dash/cash_daily.parquet")


if __name__ == "__main__":
    main()
