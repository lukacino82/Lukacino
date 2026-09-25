"""Řízení expozice místo signálu: volatility timing (Moreira & Muir 2017) a trendový filtr MA200.
Denní P&L na denních close 15:58 (1 ES = základ), náklady 0,5 b. × změna počtu kontraktů.
Alfa = úsek regrese denního P&L na denní pohyb ES (buy & hold).

python analysis/brainstorm/exposure.py <denní .pkl z features.py> <výstupní složka>
"""
import sys, os
import numpy as np, pandas as pd

F = pd.read_pickle(sys.argv[1]); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
c = F.c1558.values; N = len(c); dates = F.index
mkt = np.r_[0, np.diff(c)]
ma200 = pd.Series(c).rolling(200).mean().values
WARM = 201

def realized(n):    # směrodatná odchylka denních změn za n dní, známá na close k (pro expozici dne k+1)
    return pd.Series(mkt).rolling(n).std().values

def evaluate(w, name):
    """w[k] = expozice (kontrakty) držená od close k do close k+1."""
    w = np.nan_to_num(w); pos = np.r_[0, w[:-1]]
    pnl = pos * mkt - 0.5 * np.abs(np.diff(np.r_[0, w]))
    y = pnl[WARM:]; x = mkt[WARM:]
    X = np.c_[np.ones(len(x)), x]; b, *_ = np.linalg.lstsq(X, y, rcond=None); res = y - X @ b
    se = np.sqrt(res.var(ddof=2) * np.linalg.inv(X.T @ X)[0, 0])
    eq = np.cumsum(y); dd = (eq - np.maximum.accumulate(eq)).min()
    sh = lambda v: v.mean() / v.std() * np.sqrt(252)
    yr = dates[WARM:].year
    return dict(varianta=name, expozice_prum=np.abs(pos[WARM:]).mean(), body=eq[-1], sharpe=sh(y), maxdd_b=dd,
                vynos_dd=eq[-1] / -dd, alfa_b_den=b[0], alfa_t=b[0] / se, beta=b[1],
                sharpe_2016_21=sh(y[yr < 2022]), sharpe_2022_26=sh(y[yr >= 2022]),
                alfa_t_2016_21=None, pnl=pnl)

rows = []
bh = np.ones(N); rows.append(evaluate(bh, "Buy & hold 1 ES"))
for n in (20, 60):
    s = realized(n); w = np.minimum(np.nanmedian(s) / s, 2.0); w = w / np.nanmean(w[WARM:])
    rows.append(evaluate(w, f"Volatility timing (σ {n} dní, strop 2×, průměrná expozice 1×)"))
    w2 = np.round(w)            # jen celé kontrakty 0/1/2
    rows.append(evaluate(w2, f"Volatility timing σ {n} dní, zaokrouhleno na celé ES"))
trend = (c > ma200).astype(float)
rows.append(evaluate(trend, "Trend: long jen nad MA200"))
s = realized(20); w = np.minimum(np.nanmedian(s) / s, 2.0); w = w / np.nanmean(w[WARM:])
rows.append(evaluate(w * trend, "Volatility timing σ20 × trend MA200"))
R = pd.DataFrame([{k: v for k, v in r.items() if k != "pnl"} for r in rows])
R.round(3).to_csv(os.path.join(OUT, "expozice.csv"), index=False)
pd.to_pickle({r["varianta"]: r["pnl"] for r in rows}, os.path.join(OUT, "_expozice_pnl.pkl"))
pd.set_option("display.width", 250); print(R.drop(columns=["alfa_t_2016_21"]).round(2).to_string(index=False))
