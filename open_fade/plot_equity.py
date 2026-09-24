"""Equity křivky open±X: jen long vs. long+short, pro všechna X (1 ES, $)."""
import sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

PV = 50.0
COLORS = {10: "#2a78d6", 15: "#eb6834", 20: "#1baf7a", 40: "#eda100"}
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF})

def plot(trades_csv, out_png, title_note):
    t = pd.read_csv(trades_csv, parse_dates=["date"])
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), sharey=True)
    for ax, (label, sides) in zip(axes, [("Jen LONG (open − X)", ["LONG open-X"]),
                                          ("LONG + SHORT (open − X i open + X)", ["LONG open-X", "SHORT open+X"])]):
        for x, col in COLORS.items():
            g = t[(t.X == x) & t.side.isin(sides)].sort_values("date")
            eq = (g.pts * PV).groupby(g.date).sum().cumsum()
            ax.plot(eq.index, eq.values, color=col, lw=2, label=f"X = {x}")
            ax.annotate(f"X={x}: " + ("−" if eq.iloc[-1] < 0 else "+") + f"${abs(eq.iloc[-1]):,.0f}".replace(",", " "), (eq.index[-1], eq.iloc[-1]), xytext=(6, 0),
                        textcoords="offset points", color=INK, fontsize=8.5, va="center")
        ax.axhline(0, color=MUTED, lw=1)
        ax.grid(axis="y", color=GRID, lw=.8)
        ax.set_title(label, loc="left", color=INK, fontsize=11)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k"))
    axes[0].set_ylabel("kumulativní P/L, 1 ES")
    axes[0].legend(frameon=False, loc="lower left", fontsize=9)
    fig.suptitle(f"ES open ± X, TP 60 ticků / SL 40 ticků, výstup nejpozději 16:00 – {title_note}",
                 x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout(rect=(0, 0, 0.93, 0.95))
    fig.savefig(out_png, dpi=150); plt.close(fig)

plot("reports/open_fade/excel_souhrn_net_obchody.csv", "reports/open_fade/equity_po_nakladech.png",
     "po nákladech 0,5 b. ($25) na obchod, 07/2016–07/2026")
plot("reports/open_fade/excel_souhrn_obchody.csv", "reports/open_fade/equity_hrube.png",
     "hrubě (bez nákladů), 07/2016–07/2026")
