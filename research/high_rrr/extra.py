"""Side-split context effects, stop size relative to ATR, exit variants and pause rules."""
import os, sys, pickle
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from engine import SLS, RRS, COST, expected_longest
from search import VARS
from trail import exit_study, pause_rules, seq

OUT = os.path.join(HERE, "out")
S = pickle.load(open("/tmp/claude-0/data/hr_scan.pkl", "rb")); E, res = S["E"], S["res"]
R = pd.read_parquet(os.path.join(OUT, "search_real.parquet"))

# 1) side-split single-filter effects on win rate and expectancy
Sg = R[~R.filt.str.contains("&") & (R.filt != "(bez filtru)")].copy()
Sg["side"] = Sg.entry.str.split(" · ").str[2]
for p in ("DISC", "VAL", "TEST"):
    Sg[f"dwin_{p}"] = Sg[f"win_{p}"] - Sg[f"base_win_{p}"]
    Sg[f"dexp_{p}"] = Sg[f"exp_{p}"] - Sg[f"base_exp_{p}"]
cols = [f"dwin_{p}" for p in ("DISC", "VAL", "TEST")] + [f"dexp_{p}" for p in ("DISC", "VAL", "TEST")]
ve = Sg.groupby(["side", "filt"])[cols].mean()
ve["n_cfg"] = Sg.groupby(["side", "filt"]).size()
ve["win_consistent"] = (ve[["dwin_DISC", "dwin_VAL", "dwin_TEST"]].gt(0).all(axis=1)) | (ve[["dwin_DISC", "dwin_VAL", "dwin_TEST"]].lt(0).all(axis=1))
ve["exp_consistent"] = (ve[["dexp_DISC", "dexp_VAL", "dexp_TEST"]].gt(0).all(axis=1)) | (ve[["dexp_DISC", "dexp_VAL", "dexp_TEST"]].lt(0).all(axis=1))
ve.to_csv(os.path.join(OUT, "var_effects_side.csv"))

# 2) stop size relative to ATR: GRID long, 5D, P(stop before target) by SL/ATR bucket
g = E[(E.fam == "GRID") & (E.side == 1)].index.to_numpy()
sys.path.insert(0, os.path.join(HERE, "..", "edge_factory"))
import data as efd
_D = efd.load()
day_atr = _D.T.atr.reindex(_D.days).to_numpy()
code, ex, pnl = res["5D"]
rows = []
for j, sl in enumerate(SLS):
    ratio = sl / day_atr[E.day.to_numpy()[g]]
    for lo, hi in ((0, .1), (.1, .2), (.2, .35), (.35, .6), (.6, 1.0), (1.0, 9)):
        m = (ratio >= lo) & (ratio < hi)
        if m.sum() < 200: continue
        for r in (2, 5, 8):  # RR 3, 8, 12 index
            c = code[g[m], j, r]
            rows.append(dict(sl=sl, ratio=f"{lo}-{hi}", rr=RRS[r], n=int(m.sum()), stop=(c == -1).mean(), tp=(c == 1).mean(),
                             exp=(pnl[g[m], j, r] - COST / sl).mean()))
atrtab = pd.DataFrame(rows)
atrtab.to_csv(os.path.join(OUT, "sl_vs_atr.csv"), index=False)

# 3) exit variants + pause rules on selected configs
def m_(q): return q.to_numpy()
cfgs = [
    dict(label="Kontrola: GRID long, SL 20, 10R, 5 dní", mask=m_((E.fam == "GRID") & (E.side == 1)), sl=20, rr=10, hz="5D"),
    dict(label="GRID long v klesajícím režimu, SL 20, 10R", mask=m_((E.fam == "GRID") & (E.side == 1) & (E.regime == "down")), sl=20, rr=10, hz="5D"),
    dict(label="5d VAL long, rovnováha & RSI(M) střed, SL 20, 15R", mask=m_((E.fam == "COMP") & (E.side == 1) & (E.bal == "balance") & (E.rsiM == "mid")), sl=20, rr=15, hz="5D"),
    dict(label="Týdenní VWAP long, pod RTH VWAP & RSI(M) střed, SL 30, 10R", mask=m_((E["sub"] == "weekly VWAP") & (E.side == 1) & (E.locD == "below") & (E.rsiM == "mid")), sl=30, rr=10, hz="5D"),
    dict(label="Test 5denního low, long, SL 30, 10R", mask=m_((E.fam == "TEST") & (E["sub"] == "low 5 days")), sl=30, rr=10, hz="5D"),
]
X = exit_study(cfgs)
X.to_csv(os.path.join(OUT, "exit_variants.csv"), index=False)

per = E.period.to_numpy()
prow = []
for cf in cfgs:
    j = list(SLS).index(cf["sl"]); r = list(RRS).index(cf["rr"])
    idx = np.flatnonzero(cf["mask"])
    x = pnl[idx, j, r] - COST / cf["sl"]
    take = seq(E.i1.to_numpy()[idx].astype(np.int64), ex[idx, j, r].astype(np.int64), np.ones(len(idx), bool))
    pr = pause_rules(x[take]); pr.insert(0, "config", cf["label"]); prow.append(pr)
P = pd.concat(prow); P.to_csv(os.path.join(OUT, "pause_rules.csv"), index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 60)
print(ve[ve.win_consistent | ve.exp_consistent].round(3).sort_values(["side", "dexp_TEST"]).to_string())
print(atrtab.round(3).to_string())
print(X.round(3).to_string())
print(P.round(3).to_string())

# 4) streak length frequencies (GRID long, single-position sequence)
from trail import seq as _seq
hist_rows = []
g = np.flatnonzero(((E.fam == "GRID") & (E.side == 1)).to_numpy())
for hz in ("EOD", "5D"):
    code, ex, pnl = res[hz]
    for sl in (10, 20, 30):
        for rr in (3, 5, 10, 20):
            j = list(SLS).index(sl); r = list(RRS).index(rr)
            x = pnl[g, j, r] - COST / sl
            t = _seq(E.i1.to_numpy()[g].astype(np.int64), ex[g, j, r].astype(np.int64), np.ones(len(g), bool))
            xs = x[t]
            runs = []; cur = 0
            for v in xs:
                if v < 0: cur += 1
                else:
                    if cur: runs.append(cur)
                    cur = 0
            if cur: runs.append(cur)
            runs = np.array(runs)
            p = (xs < 0).mean()
            row = dict(hz=hz, sl=sl, rr=rr, n=len(xs), loss_rate=p, longest=runs.max())
            for k in (3, 5, 8, 10, 15, 20, 25, 30):
                row[f">={k}"] = int((runs >= k).sum())
                # i.i.d. expectation of runs >= k in n trades: n * (1-p) * p^k
                row[f"iid>={k}"] = len(xs) * (1 - p) * p ** k
            hist_rows.append(row)
H = pd.DataFrame(hist_rows); H.to_csv(os.path.join(OUT, "streak_freq.csv"), index=False)
print(H.round(1).to_string())
