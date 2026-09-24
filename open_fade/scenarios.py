"""Mřížka scénářů open±X: logika (momentum / fade) × RRR (TP:SL) × X × směr.
Výstup: souhrnná CSV + obchody pro equity grafy."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from open_fade import load_bars, run, Params

DATA = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/open_fade/scenare"
os.makedirs(OUT, exist_ok=True)
COST = 0.5
RRR = {"1:1": (40, 40), "1:1,5": (40, 60), "2:1": (80, 40), "3:1": (120, 40)}   # TP:SL v tickách
LEVELS = [10, 15, 20, 40]
df = load_bars(DATA)
rows, trades = [], []
for mode in ("momentum", "fade"):
    for rname, (tp, sl) in RRR.items():
        for x in LEVELS:
            tr = run(df, Params(level=x, tp_ticks=tp, sl_ticks=sl, cost_pts=COST, mode=mode))
            tr["mode"], tr["rrr"], tr["X"] = mode, rname, x
            trades.append(tr)
            tr["dir"] = np.where(tr.side.str.startswith("LONG"), "LONG", "SHORT")
            for d, g in list(tr.groupby("dir")) + [("OBA", tr)]:
                dec = g[g.result != "EOD"]; w = (dec.result == "TP").mean() * 100
                p = g.pts; eq = p.cumsum(); dd = (eq - eq.cummax()).min()
                yrs = p.groupby(g.date.dt.year).sum()
                rows.append(dict(logika=mode, RRR=rname, TP_ticky=tp, SL_ticky=sl, X=x, smer=d, obchodu=len(g),
                                 TP=int((g.result == "TP").sum()), SL=int((g.result == "SL").sum()),
                                 EOD=int((g.result == "EOD").sum()), TP_pct=w, breakeven_pct=100 * sl / (tp + sl),
                                 edge_pp=w - 100 * sl / (tp + sl), b_obchod=p.mean(),
                                 t=p.mean() / p.std() * np.sqrt(len(p)), usd=p.sum() * 50, maxdd_usd=dd * 50,
                                 kladne_roky=f"{(yrs > 0).sum()}/{len(yrs)}"))
            print(mode, rname, x, "hotovo", flush=True)
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/souhrn.csv", index=False)
pd.concat(trades).to_csv(f"{OUT}/obchody.csv", index=False)
print(R[R.smer == "OBA"].round(2).to_string(index=False))
