"""Denní rozpětí, propad pod open a růst nad open (RTH 09:30–16:00 ET):
kolik dní je v pásmu průměru (±10 %), nad ním a pod ním a jaký je jejich průměr.
python range_atr/above_below.py <bary .xlsx/.pkl/.txt> [výstupní .md]"""
import sys, os
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "open_fade"))
from open_fade import load_bars

df = load_bars(sys.argv[1]); t = df.index.time
rth = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
g = rth.groupby(rth.index.date)
d = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(),
                  "last": g.apply(lambda x: x.index[-1].time())})
d = d[d["last"] >= pd.Timestamp("15:45").time()]          # jen celé seance
M = {"Denní rozpětí (High − Low)": d.h - d.l,
     "Propad pod open (Open − Low)": d.o - d.l,
     "Růst nad open (High − Open)": d.h - d.o}
BAND = 0.10
out = [f"# Rozpětí, propad a růst od open: dny v průměru, nad ním a pod ním\n",
       f"ES RTH 09:30–16:00 ET, {len(d)} celých dní ({d.index[0]} – {d.index[-1]}), body.\n",
       f"„V průměru“ = do ±{BAND*100:.0f} % od průměru. Ostatní dny jsou nad pásmem, nebo pod ním.\n"]
for name, x in M.items():
    m = x.mean(); lo, hi = m * (1 - BAND), m * (1 + BAND)
    inb, above, below = x[(x >= lo) & (x <= hi)], x[x > hi], x[x < lo]
    ab, be = x[x > m], x[x <= m]
    pct = lambda s: f"{len(s)} ({len(s)/len(x)*100:.1f} %)"
    out += [f"\n## {name}\n", f"Průměr **{m:.1f} b.**, medián {x.median():.1f} b.\n",
            "| Skupina | Dní | Průměr skupiny | Rozdíl proti průměru |", "|---|---|---|---|",
            f"| V průměru ({lo:.1f}–{hi:.1f} b.) | {pct(inb)} | {inb.mean():.1f} b. | {inb.mean()-m:+.1f} b. |",
            f"| Nad pásmem (> {hi:.1f} b.) | {pct(above)} | {above.mean():.1f} b. | {above.mean()-m:+.1f} b. |",
            f"| Pod pásmem (< {lo:.1f} b.) | {pct(below)} | {below.mean():.1f} b. | {below.mean()-m:+.1f} b. |",
            f"| *Bez pásma: nad průměrem* | {pct(ab)} | {ab.mean():.1f} b. | {ab.mean()-m:+.1f} b. |",
            f"| *Bez pásma: pod průměrem* | {pct(be)} | {be.mean():.1f} b. | {be.mean()-m:+.1f} b. |"]
text = "\n".join(out) + "\n"
print(text)
if len(sys.argv) > 2: open(sys.argv[2], "w").write(text)
