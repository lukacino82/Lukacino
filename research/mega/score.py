"""Weakness / strength scores built ONLY from discovery + validation (2008-2020) of the mega scan, tested on 2021-2026.

Weakness set: the 20 single signals that occur most often in pair candidates with a positive next-night / next-day
excess (t >= 4 in 2008-15 and t >= 1 in 2016-20, regimes 'vse' and 'nad MA200'). Strength set: the same for negative
excess. Score = number of signals of the set that are true at the close. Thresholds = 80th and 95th percentile of the
score in 2008-2020. Exposure rules are fixed before looking at 2021-2026.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily as D
from strategies import metrics

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def sim(Lon, Lday, ron, rday, cash):
    """exposure overnight (close->open) and during the next RTH day (open->close); cost 0.5 pt per contract traded"""
    prev_day = np.r_[0.0, Lday[:-1]]
    cost = (np.abs(Lon - prev_day) + np.abs(Lday - Lon)) * D.COST / cash
    return Lon * ron + Lday * rday - cost


def main():
    o = D.build(); t = o["t"]; B = o["B"]
    idx = t.index
    R = pd.read_parquet(os.path.join(D.CACHE, "daily_candidates.parquet"))
    nm = pd.read_csv(os.path.join(D.CACHE, "daily_signal_names.csv")).iloc[:, 0].to_numpy()
    R = R[R.outcome.isin(["noc (close->open)", "drzeni 1d"]) & R.regime.isin(["vse", "nad MA200"])]
    sets = {}
    for lab, sgn in (("slabost", 1), ("sila", -1)):
        c = R[(R.tD * sgn >= 4) & (R.tV * sgn >= 1)]
        cnt = pd.concat([pd.Series(nm[c.i]), pd.Series(nm[c.j])]).value_counts()
        cnt = cnt[~cnt.index.str.startswith("kontrola")]
        sets[lab] = list(cnt.head(20).index)
        print(lab, len(c), "kandidatu;", sets[lab])
    pd.DataFrame({k: pd.Series(v) for k, v in sets.items()}).to_csv(os.path.join(OUT, "score_signaly.csv"), index=False)
    sw = B[sets["slabost"]].sum(axis=1).to_numpy(); ss = B[sets["sila"]].sum(axis=1).to_numpy()
    C = t.C.to_numpy(); O = t.O.to_numpy(); cash = t.cash.to_numpy(); A = t.atr.to_numpy()
    ron = (np.r_[O[1:], np.nan] - C) / cash; rday = (np.r_[C[1:], np.nan] - np.r_[O[1:], np.nan]) / cash
    dv = idx < "2021-01-01"; warm = idx >= "2009-06-01"
    k1, k2 = np.quantile(sw[dv & warm], [0.80, 0.95]); s1 = np.quantile(ss[dv & warm], 0.90)
    print("prahy slabost", k1, k2, "sila", s1)
    # score -> next day outcome, by period
    rows = []
    y1 = (np.r_[C[1:], np.nan] - C) / A; yon = (np.r_[O[1:], np.nan] - C) / A
    for lab, m in (("2009-2015", (idx < "2016-01-01") & warm), ("2016-2020", (idx >= "2016-01-01") & dv), ("2021-2026 (holdout)", ~dv)):
        for nm_, sel in (("slabost < %g" % k1, sw < k1), ("slabost %g-%g" % (k1, k2), (sw >= k1) & (sw < k2)), ("slabost >= %g" % k2, sw >= k2),
                         ("sila >= %g" % s1, ss >= s1), ("vsechny dny", np.ones(len(idx), bool))):
            q = m & sel & np.isfinite(y1)
            rows.append(dict(obdobi=lab, skupina=nm_, dnu=int(q.sum()), dalsi_den_atr=y1[q].mean(), t=y1[q].mean() / y1[q].std() * np.sqrt(q.sum()),
                             noc_atr=yon[q].mean(), p_rust=(y1[q] > 0).mean(), dalsi_den_pct=((np.r_[C[1:], np.nan] - C) / cash)[q].mean() * 100))
    S = pd.DataFrame(rows); S.round(4).to_csv(os.path.join(OUT, "score_dalsi_den.csv"), index=False)
    pd.set_option("display.width", 250); print(S.round(3).to_string())
    weak1 = sw >= k1; weak2 = sw >= k2; strong = (ss >= s1) & ~weak1
    one = np.ones(len(idx))
    strat = {
        "Buy & hold 1x": (one, one),
        "S1: slabost -> 2x (noc i den)": (np.where(weak1, 2.0, 1.0),) * 2,
        "S2: slabost 2x, silna slabost 3x": (np.where(weak2, 3.0, np.where(weak1, 2.0, 1.0)),) * 2,
        "S3: slabost -> +1x jen pres noc": (np.where(weak1, 2.0, 1.0), one),
        "S4: S2 a pri sile 0.5x": (np.where(weak2, 3.0, np.where(weak1, 2.0, np.where(strong, 0.5, 1.0))),) * 2,
        "S5: jen slabost (jinak mimo trh)": (np.where(weak1, 1.0, 0.0),) * 2,
        "S6: jen slabost, silna 2x": (np.where(weak2, 2.0, np.where(weak1, 1.0, 0.0)),) * 2,
        "S7: slabost 2x jen pres noc, jinak mimo trh": (np.where(weak1, 2.0, 0.0), np.zeros(len(idx))),
    }
    m = warm & np.isfinite(ron) & np.isfinite(rday)
    rows = []; curves = {}
    bh = sim(one[m], one[m], ron[m], rday[m], cash[m])
    for nm_, (Lo, Ld) in strat.items():
        ret = sim(Lo[m], Ld[m], ron[m], rday[m], cash[m]); curves[nm_] = np.cumprod(1 + ret)
        row = dict(strategie=nm_, prum_expozice=(Lo[m].mean() + Ld[m].mean()) / 2, **metrics(ret, bh, idx[m]))
        for lab, a, b in (("2009_15", "2009-01-01", "2016-01-01"), ("2016_20", "2016-01-01", "2021-01-01"), ("2021_26", "2021-01-01", "2030-01-01")):
            mm = (idx[m] >= a) & (idx[m] < b); x = metrics(ret[mm], bh[mm], idx[m][mm])
            for k in ("CAGR", "Sharpe", "maxDD", "alfa_t"):
                row[f"{k}_{lab}"] = x[k]
        rows.append(row)
    T = pd.DataFrame(rows); T.loc[0, ["alfa_t", "alfa_t_2009_15", "alfa_t_2016_20", "alfa_t_2021_26"]] = np.nan
    T.round(4).to_csv(os.path.join(OUT, "score_strategie.csv"), index=False)
    pd.DataFrame(curves, index=idx[m]).to_parquet(os.path.join(OUT, "score_equity.parquet"))
    print(T[["strategie", "prum_expozice", "CAGR", "Sharpe", "maxDD", "alfa_rok", "alfa_t", "let_lepsich_nez_BH", "CAGR_2009_15", "CAGR_2016_20",
             "CAGR_2021_26", "Sharpe_2021_26", "maxDD_2021_26", "alfa_t_2021_26"]].round(3).to_string())


if __name__ == "__main__":
    main()
