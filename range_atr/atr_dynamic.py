"""Open ± k·ATR s TP/SL v násobcích ATR (dynamicky každý den). Ověřuje, zda
dynamické TP/SL vytvoří hranu, kterou pevné body nemají."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "open_fade"))
from open_fade import load_bars, simulate_day, Params, TICK

df = load_bars(sys.argv[1]); OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/range_atr"
daily = pd.read_pickle(os.path.join(OUT, "daily.pkl"))
t = df.index.time
rth = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
days = [(pd.Timestamp(d), (g.open.values, g.high.values, g.low.values, g.close.values, g.index.time))
        for d, g in rth.groupby(rth.index.date) if pd.Timestamp(d) in daily.index]
atr = daily.atr
COST = 0.5; SL_ATR = 0.25
RRR = {"1:1": 1.0, "1:1,5": 1 / 1.5, "2:1": 2.0, "3:1": 3.0}
rows, trades = [], []
for mode in ("momentum", "fade"):
    for k in (0.25, 0.5, 0.75):
        for rname, rr in RRR.items():
            res = []
            for d, arr in days:
                a = atr.get(d)
                if not np.isfinite(a): continue
                sl_t = max(1, round(SL_ATR * a / TICK)); tp_t = max(1, round(rr * SL_ATR * a / TICK))
                p = Params(level=round(k * a / TICK) * TICK, tp_ticks=tp_t, sl_ticks=sl_t, mode=mode)
                for direction, side in ((1, "LONG"), (-1, "SHORT")):
                    r = simulate_day(*arr, p, direction)
                    if r: res.append((d, side, r[0], (r[1] - COST) / (sl_t * TICK), r[1] - COST))
            tr = pd.DataFrame(res, columns=["date", "side", "result", "R", "pts"])
            tr["mode"], tr["k"], tr["rrr"] = mode, k, rname; trades.append(tr)
            for side, g in list(tr.groupby("side")) + [("OBA", tr)]:
                dec = g[g.result != "EOD"]; w = (dec.result == "TP").mean() * 100; be = 100 / (1 + rr)
                rows.append(dict(logika=mode, k_ATR=k, RRR=rname, smer=side, obchodu=len(g), TP_pct=w, breakeven=be,
                                 edge_pp=w - be, R_obchod=g.R.mean(), t=g.R.mean() / g.R.std() * np.sqrt(len(g)),
                                 usd=g.pts.sum() * 50))
R = pd.DataFrame(rows); R.to_csv(os.path.join(OUT, "atr_dynamic.csv"), index=False)
pd.concat(trades).to_csv(os.path.join(OUT, "atr_dynamic_obchody.csv"), index=False)
pd.set_option("display.width", 200)
print(R[R.smer == "OBA"].round(2).to_string(index=False))
print("\nNejlepších 8 (všechny směry):")
print(R.sort_values("t", ascending=False).head(8).round(2).to_string(index=False))
