"""Apply the robustness gates, build benchmarks and export everything the report needs."""
from __future__ import annotations

import json
import os
import pickle

import numpy as np
import pandas as pd

from engine import PERIODS, stats

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
D = "/tmp/claude-0/data/"
COST = 0.5
PER = [p for p, _, _ in PERIODS]


def gates(a, b):
    """a = ES3000 row, b = Excel volume-bar row of the same strategy."""
    g = {}
    g["G1 net>0 @0.5 a @1.0 b."] = bool(a.exp > 0 and a.exp_stress > 0)
    g["G2 kladná ve DISC/VAL/OOS"] = bool(all(a[f"exp|{p}"] > 0 for p in PER[1:]))
    pre_n = b[f"n|{PER[0]}"]
    g["G3 kladná v PRE 2016-18"] = bool(pre_n >= 15 and b[f"exp|{PER[0]}"] > 0)
    g["G4 edge vs. náhodný long t>=2"] = bool(a.t_edge >= 2.0)
    g["G5 plató TP/SL >=60 %"] = bool(a.plateau >= 0.6)
    g["G6 walk-forward > 0"] = bool(a.wf_net > 0)
    g["G7 parita (Excel data) > 0"] = bool(b.exp > 0)
    return g


def verdict(g, a):
    n = sum(g.values())
    if n == len(g):
        return "NASADIT"
    if a.n >= 60 and g["G1 net>0 @0.5 a @1.0 b."] and a.t_edge >= 1.5 and g["G6 walk-forward > 0"] and n >= 5:
        return "SLEDOVAT (paper)"
    return "ZAMÍTNOUT"


def main():
    s = pd.read_csv(os.path.join(OUT, "summary_raw.csv"))
    A = s[s.src == "es1m"].set_index("strategy")
    B = s[s.src == "esvol"].set_index("strategy")
    rows = []
    for name, a in A.iterrows():
        b = B.loc[name]
        g = gates(a, b)
        r = dict(strategy=name, phase=a.phase, rule=a.rule, exit=a.exit, n=int(a.n), exp=a.exp,
                 exp_stress=a.exp_stress, win=a.win, pf=a.pf, net=a.net, maxdd=a.maxdd,
                 null_exp=a.null_exp, edge=a.edge, t_edge=a.t_edge, plateau=a.plateau, wf_net=a.wf_net,
                 **{f"exp|{p}": a[f"exp|{p}"] for p in PER[1:]},
                 pre_n=int(b[f"n|{PER[0]}"]), pre_exp=b[f"exp|{PER[0]}"], xl_exp=b.exp, xl_t_edge=b.t_edge,
                 gates_passed=sum(g.values()), **g)
        r["verdict"] = verdict(g, a)
        rows.append(r)
    summ = pd.DataFrame(rows).sort_values(["gates_passed", "t_edge"], ascending=False)
    summ.to_csv(os.path.join(OUT, "summary.csv"), index=False)

    tr = pd.read_csv(os.path.join(OUT, "trades.csv"), parse_dates=["date"])
    t1 = tr[tr.src == "es1m"].copy()
    t1["net"] = t1.gross - COST

    # ATR-normalised expectancy per period (removes the effect of ES tripling in price)
    S = pickle.load(open(D + "es1m_sess.pkl", "rb"))
    atr = S.R.atr20
    t1["R"] = t1.net / atr.reindex(t1.date).to_numpy()
    rnorm = t1.pivot_table(index="strategy", columns="period", values="R", aggfunc="mean")
    rnorm.to_csv(os.path.join(OUT, "exp_in_atr_units.csv"))

    # benchmarks on ES3000 days (points, 1 contract)
    adjC = S.R.pclose_adj.shift(-1).ffill()  # adjusted RTH close of the day
    adjC.iloc[-1] = S.dC[-1] + (S.R.pclose_adj.iloc[-1] - S.pdc[-1])
    bh = adjC - adjC.iloc[0]
    rth = pd.Series(S.dC - S.dO, index=S.dates).cumsum()
    bench = pd.DataFrame({"buy_hold": bh, "rth_long_open_close": rth})
    bench.to_csv(os.path.join(OUT, "benchmarks.csv"))

    # expected best t-stat among N zero-edge strategies (multiple-testing yardstick)
    rng = np.random.default_rng(1)
    nstrat = len(summ)
    mx = np.abs(rng.standard_normal((20000, nstrat))).max(1)
    yard = dict(n_strategies=nstrat, median_max_t=float(np.median(mx)), p95_max_t=float(np.quantile(mx, 0.95)))

    # equity curves (net 0.5) + watchlist portfolio
    eq = {}
    for name, g in t1.groupby("strategy"):
        eq[name] = g.sort_values("date")[["date", "net"]]
    watch = summ[summ.verdict != "ZAMÍTNOUT"].strategy.tolist()
    port = t1[t1.strategy.isin(watch)].groupby("date").net.sum().sort_index()
    pst = stats(port.to_numpy()) if len(port) else {}
    pper = {p: float(t1[t1.strategy.isin(watch) & (t1.period == p)].groupby("date").net.sum().mean())
            for p in PER[1:]} if watch else {}
    corr = t1[t1.strategy.isin(watch)].pivot_table(index="date", columns="strategy", values="net").fillna(0).corr()

    # daily range distribution
    r = pd.read_csv(os.path.join(OUT, "ranges.csv"), parse_dates=["date"])
    rng_stats = {}
    for src, g in r.groupby("src"):
        x = g["range"].dropna()
        m, sd = x.mean(), x.std()
        ra = g.range_atr.dropna()
        rng_stats[src] = dict(days=int(len(x)), mean=m, median=x.median(), sd=sd,
                              within_1sd=float(((x > m - sd) & (x < m + sd)).mean()),
                              below_mean=float((x < m).mean()), above_mean=float((x > m).mean()),
                              p10=x.quantile(.1), p25=x.quantile(.25), p75=x.quantile(.75), p90=x.quantile(.9),
                              skew=float(x.skew()), cv_points=float(sd / m), cv_atr=float(ra.std() / ra.mean()),
                              range_atr_median=float(ra.median()),
                              open_low_med=float(g.open_low.median()), high_open_med=float(g.high_open.median()),
                              by_year=g.groupby(g.date.dt.year)["range"].mean().round(1).to_dict())
    json.dump(dict(yard=yard, watch=watch, portfolio=dict(stats={k: float(v) for k, v in pst.items()}, per=pper),
                   ranges=rng_stats, corr=corr.round(2).to_dict()),
              open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=float)
    pickle.dump(dict(eq=eq, port=port, bench=bench, rnorm=rnorm), open(os.path.join(OUT, "series.pkl"), "wb"))
    pd.set_option("display.width", 250)
    print(summ[["strategy", "n", "exp", "t_edge", "gates_passed", "verdict"]].to_string())
    print(rnorm.round(3).loc[watch] if watch else "")
    print(json.dumps(yard), pst, pper)
    print(json.dumps(rng_stats, default=float, indent=0)[:1500])


if __name__ == "__main__":
    main()
