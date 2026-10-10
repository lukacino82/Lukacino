"""Where do the long losing streaks happen? Context of trades inside streaks >= 10 vs all trades,
and does tying the stop to volatility (SL/ATR band) bring the tail back to i.i.d.?"""
import os, sys, pickle
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "edge_factory"))
import numpy as np, pandas as pd
from engine import SLS, RRS, COST
from trail import seq
import data as efd

OUT = os.path.join(HERE, "out")
S = pickle.load(open("/tmp/claude-0/data/hr_scan.pkl", "rb")); E, res = S["E"], S["res"]
D = efd.load()
atr = D.T.atr.reindex(D.days).to_numpy()
E["sl_atr_10"] = 10 / atr[E.day.to_numpy()]
E["year"] = pd.DatetimeIndex(D.days[E.day.to_numpy()]).year

def runs_with_members(x):
    lab = np.zeros(len(x), int); cur = []; out = []
    for i, v in enumerate(x):
        if v < 0: cur.append(i)
        else:
            if cur: out.append(cur)
            cur = []
    if cur: out.append(cur)
    return out

rows, tail_rows = [], []
g = np.flatnonzero(((E.fam == "GRID") & (E.side == 1)).to_numpy())
for hz, sl, rr in (("EOD", 10, 5), ("5D", 20, 10), ("5D", 10, 10), ("5D", 30, 10)):
    code, ex, pnl = res[hz]; j = list(SLS).index(sl); r = list(RRS).index(rr)
    x = pnl[g, j, r] - COST / sl
    t = seq(E.i1.to_numpy()[g].astype(np.int64), ex[g, j, r].astype(np.int64), np.ones(len(g), bool))
    Et = E.iloc[g[t]].copy(); Et["x"] = x[t]
    Et["slatr"] = sl / atr[Et.day.to_numpy()]
    in_long = np.zeros(len(Et), bool)
    for run in runs_with_members(Et.x.to_numpy()):
        if len(run) >= 10: in_long[run] = True
    Et["in_long"] = in_long
    lab = f"{hz} SL{sl} {rr}R"
    rows.append(dict(config=lab, trades=len(Et), in_long_streaks=int(in_long.sum()),
                     slatr_all=Et.slatr.median(), slatr_streak=Et.slatr[in_long].median(),
                     regime_down_all=(Et.regime == "down").mean(), regime_down_streak=(Et.regime[in_long] == "down").mean(),
                     bal_trend_all=(Et.bal == "trend").mean(), bal_trend_streak=(Et.bal[in_long] == "trend").mean()))
    yy = Et.groupby("year").agg(trades=("x", "size"), streak_trades=("in_long", "sum"))
    yy["config"] = lab; tail_rows.append(yy.reset_index())
    # stop tied to volatility: only trade when SL/ATR in a band
    for lo, hi in ((0, 0.2), (0.2, 0.35), (0.35, 0.6), (0.6, 9)):
        ra = sl / atr[E.day.to_numpy()[g]]
        m = (ra >= lo) & (ra < hi)
        tt = seq(E.i1.to_numpy()[g].astype(np.int64), ex[g, j, r].astype(np.int64), m)
        xs = x[tt]
        if len(xs) < 50: continue
        p = (xs < 0).mean(); runs = [len(q) for q in runs_with_members(xs)]
        runs = np.array(runs)
        rows.append(dict(config=f"{lab} · SL/ATR {lo}-{hi}", trades=len(xs), exp=xs.mean(), loss_rate=p, longest=runs.max(),
                         ge10=int((runs >= 10).sum()), iid_ge10=len(xs) * (1 - p) * p ** 10,
                         ge15=int((runs >= 15).sum()), iid_ge15=len(xs) * (1 - p) * p ** 15))
R = pd.DataFrame(rows); Y = pd.concat(tail_rows)
R.to_csv(os.path.join(OUT, "streak_context.csv"), index=False); Y.to_csv(os.path.join(OUT, "streak_years.csv"), index=False)
pd.set_option("display.width", 250)
print(R.round(3).to_string())
print(Y.pivot_table(index="year", columns="config", values="streak_trades", aggfunc="sum").to_string())
