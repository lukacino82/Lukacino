"""Graf: rozdělení denního rozpětí vs. Gauss, rozpětí po letech, rozpětí/ATR, dosah od open."""
import os, sys
import numpy as np, pandas as pd
from statistics import NormalDist
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
OUT = sys.argv[1] if len(sys.argv) > 1 else "reports/range_atr"
d = pd.read_pickle(os.path.join(OUT, "daily.pkl")); x = d.dropna()
BLUE, ORANGE, GRAYB, INK, MUTED, GRID, SURF = "#2a78d6", "#eb6834", "#86b6ef", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF})
fig, ax = plt.subplots(2, 2, figsize=(15, 9.5))
# 1) histogram + Gauss
r = d.range; m, s = r.mean(), r.std(); a = ax[0, 0]
bins = np.arange(0, 200, 5)
a.hist(r.clip(upper=199), bins=bins, color=BLUE, edgecolor=SURF, linewidth=1, label="skutečné dny")
xs = np.linspace(0, 200, 400); N = NormalDist(m, s)
a.plot(xs, [N.pdf(v) * len(r) * 5 for v in xs], color=ORANGE, lw=2, label=f"Gaussova křivka (μ {m:.1f}, σ {s:.1f})")
for v, lab in ((r.median(), f"medián {r.median():.1f}"), (m, f"průměr {m:.1f}")):
    a.axvline(v, color=INK, lw=1, ls="--"); a.text(v + 1, a.get_ylim()[1] * 0.93 if lab.startswith("p") else a.get_ylim()[1] * 0.85, lab, fontsize=9, color=INK)
a.set_title(f"Denní RTH rozpětí ES (H−L), {len(r)} dní 2016–2026\n60,5 % dní pod průměrem · ±1σ obsahuje 83 % dní (Gauss 68 %)",
            loc="left", color=INK, fontsize=10.5)
a.set_xlabel("rozpětí dne (body), dny nad 200 b. v posledním sloupci"); a.set_ylabel("počet dní"); a.legend(frameon=False)
a.grid(axis="y", color=GRID, lw=.8)
# 2) po letech
a = ax[0, 1]; y = d.groupby(d.index.year).agg(r=("range", "mean"), p=("range_pct", "mean"))
a.bar(y.index, y.r, color=BLUE, width=0.7)
for yr, v in y.r.items(): a.text(yr, v + 1, f"{v:.0f}", ha="center", fontsize=9, color=INK)
a.axhline(m, color=ORANGE, lw=1.5, ls="--"); a.text(y.index[0] - 0.4, m + 2, f"celkový průměr {m:.1f} b.", color=INK, fontsize=9)
a.set_title("Průměrné rozpětí po letech: 13 až 74 bodů\npevný TP/SL v bodech nesedí na žádný rok", loc="left", color=INK, fontsize=10.5)
a.set_ylabel("průměrné rozpětí (body)"); a.set_xticks(y.index); a.grid(axis="y", color=GRID, lw=.8)
# 3) rozpětí / ATR
a = ax[1, 0]
a.hist(x.r_atr.clip(upper=3.95), bins=np.arange(0, 4.01, 0.1), color=BLUE, edgecolor=SURF, linewidth=1)
for q, lab, hy in ((0.25, "25 %", 0.93), (0.5, "medián", 0.78), (0.75, "75 %", 0.63), (0.9, "90 %", 0.48)):
    v = x.r_atr.quantile(q); a.axvline(v, color=INK, lw=1, ls="--"); a.text(v + 0.04, a.get_ylim()[1] * hy, f"{lab} {v:.2f}×", fontsize=8.5, color=INK)
a.set_title("Rozpětí dne / ATR(14) z minulých dní\nATR vysvětlí 42 % rozpětí (korelace 0,65)", loc="left", color=INK, fontsize=10.5)
a.set_xlabel("rozpětí dne v násobcích ATR"); a.set_ylabel("počet dní"); a.grid(axis="y", color=GRID, lw=.8)
# 4) dosah od open
a = ax[1, 1]; ks = [0.1, 0.25, 0.5, 0.75, 1.0]
up = [((x.up / x.atr) >= k).mean() * 100 for k in ks]; dn = [((x.down / x.atr) >= k).mean() * 100 for k in ks]
w = 0.38; pos = np.arange(len(ks))
a.bar(pos - w / 2, up, w, color=BLUE, label="nahoru od open"); a.bar(pos + w / 2, dn, w, color=GRAYB, label="dolů od open")
for i in range(len(ks)):
    a.text(pos[i] - w / 2, up[i] + 1, f"{up[i]:.0f} %", ha="center", fontsize=8.5, color=INK)
    a.text(pos[i] + w / 2, dn[i] + 1, f"{dn[i]:.0f} %", ha="center", fontsize=8.5, color=INK)
a.set_xticks(pos, [f"{k}×ATR" for k in ks]); a.set_ylabel("% dní")
a.set_title("Jak často cena dojde od open aspoň k×ATR\nnahoru i dolů skoro stejně: směr z toho nevyčteš", loc="left", color=INK, fontsize=10.5)
a.legend(frameon=False); a.grid(axis="y", color=GRID, lw=.8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "rozpeti_atr.png"), dpi=140)
