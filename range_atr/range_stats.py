"""Rozdělení denního RTH rozpětí ES: Gauss vs. skutečnost, extrémy, ATR predikce."""
import sys, os
import numpy as np, pandas as pd
from statistics import NormalDist
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "open_fade"))
from open_fade import load_bars

df = load_bars(sys.argv[1]); OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/range_atr"
t = df.index.time
rth = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
g = rth.groupby(rth.index.date)
d = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(), "c": g.close.last(),
                  "last": g.apply(lambda x: x.index[-1].time())})
d = d[d["last"] >= pd.Timestamp("15:45").time()].drop(columns="last"); d.index = pd.to_datetime(d.index)
d["range"] = d.h - d.l; d["up"] = d.h - d.o; d["down"] = d.o - d.l
d["range_pct"] = d.range / d.o * 100
d["atr"] = d.range.rolling(14).mean().shift(1)          # jen minulé dny
d["r_atr"] = d.range / d.atr
d.to_pickle(os.path.join(OUT, "daily.pkl"))
r = d.range; m, s = r.mean(), r.std(); N = NormalDist(m, s)
print(f"dní {len(d)}, {d.index[0].date()}–{d.index[-1].date()}")
print(f"průměr {m:.2f}  medián {r.median():.2f}  σ {s:.2f}  šikmost {r.skew():.2f}  špičatost {r.kurt():.2f}")
print(f"pod průměrem: {(r < m).mean()*100:.1f} % dní, nad průměrem: {(r > m).mean()*100:.1f} %")
for k in (1, 2, 3):
    lo, hi = m - k*s, m + k*s
    emp = ((r >= lo) & (r <= hi)).mean()*100; gau = (N.cdf(hi) - N.cdf(lo))*100
    print(f"±{k}σ ({max(lo,0):.1f}–{hi:.1f} b.): skutečnost {emp:.1f} % ({int(emp*len(r)/100)} dní) | Gauss {gau:.1f} %"
          f" | pod: {(r<lo).mean()*100:.1f} %, nad: {(r>hi).mean()*100:.1f} % (Gauss {(1-N.cdf(hi))*100:.2f} %)")
print("pásma kolem průměru:")
for a, b in ((0, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 80), (80, 100), (100, 150), (150, 1e9)):
    x = ((r >= a) & (r < b)); print(f"  {a:>3}–{b if b < 1e8 else '∞':>3} b.: {x.sum():4d} dní ({x.mean()*100:5.1f} %)")
print("percentily:", {p: round(r.quantile(p/100), 1) for p in (5, 10, 25, 50, 75, 90, 95, 99)})
print("\npo letech (průměr rozpětí, % z ceny):")
print(d.groupby(d.index.year).agg(rozpeti=("range", "mean"), cena=("o", "mean"), pct=("range_pct", "mean")).round(2).to_string())
x = d.dropna()
print(f"\nATR(14) predikce: corr(rozpětí, ATR včera) = {x.range.corr(x.atr):.3f}, R² = {x.range.corr(x.atr)**2:.2f}")
print(f"rozpětí/ATR: průměr {x.r_atr.mean():.2f}, medián {x.r_atr.median():.2f}, σ {x.r_atr.std():.2f}, šikmost {x.r_atr.skew():.2f}")
print("rozpětí/ATR percentily:", {p: round(x.r_atr.quantile(p/100), 2) for p in (5, 10, 25, 50, 75, 90, 95)})
ua = (x.up / x.atr); da = (x.down / x.atr)
print("P(cena dosáhne od open aspoň k×ATR):")
for k in (0.1, 0.25, 0.5, 0.75, 1.0):
    print(f"  k={k}: nahoru {(ua >= k).mean()*100:.1f} %, dolů {(da >= k).mean()*100:.1f} %, aspoň jedním směrem {((ua>=k)|(da>=k)).mean()*100:.1f} %")
