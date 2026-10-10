"""Does skipping longs inside a running correction shorten loss streaks (beyond having fewer trades)?"""
import os, sys, pickle
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "edge_factory"))
import numpy as np, pandas as pd
from engine import SLS, RRS, COST
from trail import seq
import data as efd

S = pickle.load(open("/tmp/claude-0/data/hr_scan.pkl", "rb")); E, res = S["E"], S["res"]; D = efd.load()
atr = D.T.atr.reindex(D.days).to_numpy()
corr = ((E.bal == "trend") | (E.locW == "<-2sd") | (E.dd == "3-7%")).to_numpy()
rows = []
for fam_lab, fm in (("GRID long", (E.fam == "GRID") & (E.side == 1)), ("Test 5denního low", (E.fam == "TEST") & (E["sub"] == "low 5 days")),
                    ("5d VAL long", (E.fam == "COMP") & (E.side == 1))):
    g = np.flatnonzero(fm.to_numpy())
    for hz in ("EOD", "5D"):
        code, ex, pnl = res[hz]
        for sl in (10, 20, 30):
            for rr in (3, 5, 10):
                j = list(SLS).index(sl); r = list(RRS).index(rr)
                for flab, keep in (("bez filtru", np.ones(len(g), bool)), ("bez rozjeté korekce", ~corr[g])):
                    t = seq(E.i1.to_numpy()[g].astype(np.int64), ex[g, j, r].astype(np.int64), keep)
                    x = pnl[g[t], j, r] - COST / sl
                    per = E.period.to_numpy()[g[t]]
                    runs, cur = [], 0
                    for v in x:
                        if v < 0: cur += 1
                        else:
                            if cur: runs.append(cur)
                            cur = 0
                    if cur: runs.append(cur)
                    runs = np.array(runs); p = (x < 0).mean(); n = len(x)
                    rows.append(dict(entry=fam_lab, hz=hz, sl=sl, rr=rr, filt=flab, n=n, loss=p, exp=x.mean(),
                                     exp_DISC=x[per == "DISC"].mean(), exp_VAL=x[per == "VAL"].mean(), exp_TEST=x[per == "TEST"].mean(),
                                     longest=runs.max(), ge10=int((runs >= 10).sum()), iid_ge10=n * (1 - p) * p ** 10,
                                     ge10_per1000=(runs >= 10).sum() / n * 1000))
R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "out", "corr_filter.csv"), index=False)
pd.set_option("display.width", 250)
print(R.round(3).to_string())
