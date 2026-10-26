"""B4/A5: is any weekday or hour different from the rest? t-test of each group vs all others, and how often the
'best' weekday of one year is also the best the next year (persistence)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stats as S


def ttab(df, col, val):
    rows = []
    for k, g in df.groupby(col):
        o = df[df[col] != k][val]
        t, p = st.ttest_ind(g[val], o, equal_var=False)
        rows.append(dict(skupina=k, n=len(g), prumer=g[val].mean(), ostatni=o.mean(), t=t, p=p))
    return pd.DataFrame(rows)


def main():
    c = S.cash()
    g = S.daily_cash(c)
    b = ttab(g, "den", "ret"); b["test"] = "vynos dne %"
    r = ttab(g, "den", "rozpeti_pct"); r["test"] = "rozpeti dne %"
    g["sell"] = (g.ret <= g.groupby("rok").ret.transform(lambda x: x.quantile(0.1))).astype(float)
    s = ttab(g, "den", "sell"); s["test"] = "podil vyprodeju (spodnich 10 % dnu roku)"
    # persistence of the best weekday
    piv = g.groupby(["rok", "den"]).ret.mean().unstack()[S.WD[:5]]
    best = piv.idxmax(axis=1)
    pers = (best.shift() == best).iloc[1:].mean()
    out = pd.concat([b, r, s])
    out.round(4).to_csv(os.path.join(S.OUT, "B4_dny_signifikance.csv"), index=False)
    # hours (cash % return of each hour)
    h = c.set_index("ts").resample("1h").agg({"O": "first", "C": "last"}).dropna()
    h["ret"] = (h.C / h.O - 1) * 100; h["hodina"] = h.index.hour
    a = ttab(h.reset_index(), "hodina", "ret")
    a.round(4).to_csv(os.path.join(S.OUT, "A5_hodiny_signifikance.csv"), index=False)
    pd.set_option("display.width", 200)
    print(out.round(3).to_string()); print("perzistence nejlepsiho dne (nahoda 0.2):", round(pers, 3))
    print(a.round(3).to_string())


if __name__ == "__main__":
    main()
