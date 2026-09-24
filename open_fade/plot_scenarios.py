"""Heatmapa všech scénářů + mřížky equity křivek (RRR × směr, čáry = X)."""
import sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

D = sys.argv[1] if len(sys.argv) > 1 else "reports/open_fade/scenare"
R = pd.read_csv(f"{D}/souhrn.csv"); T = pd.read_csv(f"{D}/obchody.csv", parse_dates=["date"])
T["dir"] = np.where(T.side.str.startswith("LONG"), "LONG", "SHORT")
RRR = ["1:1", "1:1,5", "2:1", "3:1"]; XS = [10, 15, 20, 40]; DIRS = ["LONG", "SHORT", "OBA"]
XCOL = {10: "#2a78d6", 15: "#eb6834", 20: "#1baf7a", 40: "#eda100"}
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "figure.facecolor": SURF, "axes.facecolor": SURF})
DIRNAME = {"momentum": {"LONG": "LONG (open + X)", "SHORT": "SHORT (open − X)", "OBA": "LONG + SHORT"},
           "fade": {"LONG": "LONG (open − X)", "SHORT": "SHORT (open + X)", "OBA": "LONG + SHORT"}}
usd = lambda v: ("−" if v < 0 else "+") + f"${abs(v)/1000:,.1f}k"

# ---------- heatmapa ----------
cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])
lim = R.usd.abs().max()
fig, axes = plt.subplots(2, 3, figsize=(15, 8.6))
for r, mode in enumerate(["momentum", "fade"]):
    for c, d in enumerate(DIRS):
        ax = axes[r, c]
        sub = R[(R.logika == mode) & (R.smer == d)]
        M = sub.pivot(index="X", columns="RRR", values="usd").loc[XS, RRR].values
        Tt = sub.pivot(index="X", columns="RRR", values="t").loc[XS, RRR].values
        ax.imshow(M, cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
        for i in range(4):
            for j in range(4):
                ax.text(j, i - 0.12, usd(M[i, j]), ha="center", va="center", fontsize=10, color=INK, weight="bold")
                ax.text(j, i + 0.2, f"t {Tt[i, j]:+.1f}", ha="center", va="center", fontsize=8.5, color=MUTED)
        ax.set_xticks(range(4), RRR); ax.set_yticks(range(4), [f"X = {x}" for x in XS])
        ax.set_xticks(np.arange(-.5, 4), minor=True); ax.set_yticks(np.arange(-.5, 4), minor=True)
        ax.grid(which="minor", color=SURF, lw=3); ax.tick_params(which="minor", length=0)
        for s in ax.spines.values(): s.set_visible(False)
        ax.set_title(("MOMENTUM" if mode == "momentum" else "FADE") + " · " + DIRNAME[mode][d],
                     loc="left", color=INK, fontsize=11)
        if c == 0: ax.set_ylabel("vzdálenost od open")
        if r == 1: ax.set_xlabel("RRR (TP : SL)")
fig.suptitle("ES open ± X: čistý výsledek za 10 let po nákladech 0,5 b./obchod (1 ES, 07/2016–07/2026) · "
             "modrá = zisk, červená = ztráta · t > 2 by bylo významné", x=0.01, ha="left", color=INK, fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(f"{D}/heatmapa_vysledku.png", dpi=150); plt.close(fig)

# ---------- equity mřížky ----------
ymin = ymax = 0
curves = {}
for mode in ("momentum", "fade"):
    for rr in RRR:
        for d in DIRS:
            for x in XS:
                g = T[(T["mode"] == mode) & (T.rrr == rr) & (T.X == x)]
                if d != "OBA": g = g[g.dir == d]
                eq = (g.pts * 50).groupby(g.date).sum().sort_index().cumsum()
                curves[(mode, rr, d, x)] = eq; ymin = min(ymin, eq.min()); ymax = max(ymax, eq.max())
for mode in ("momentum", "fade"):
    fig, axes = plt.subplots(4, 3, figsize=(16, 15), sharex=True, sharey=True)
    for r, rr in enumerate(RRR):
        tp, sl = R[R.RRR == rr][["TP_ticky", "SL_ticky"]].iloc[0]
        for c, d in enumerate(DIRS):
            ax = axes[r, c]
            ends = []
            for x in XS:
                eq = curves[(mode, rr, d, x)]
                ax.plot(eq.index, eq.values, color=XCOL[x], lw=1.6, label=f"X = {x}")
                ends.append([eq.iloc[-1], x, eq.index[-1]])
            # popisky na konci křivek s minimálním rozestupem (bez překryvu)
            ends.sort(key=lambda e: e[0]); gap = (ymax - ymin) * 0.045
            ys = [e[0] for e in ends]
            for k in range(1, len(ys)):
                ys[k] = max(ys[k], ys[k - 1] + gap)
            xend = max(e[2] for e in ends)
            for (val, x, _), yl in zip(ends, ys):
                ax.annotate(f"X={x}: {usd(val)}", (xend, yl), xytext=(5, 0), textcoords="offset points",
                            fontsize=8, color=INK, va="center")
                ax.plot([xend], [yl], marker="s", ms=4, color=XCOL[x], clip_on=False)
            ax.axhline(0, color=MUTED, lw=1); ax.grid(axis="y", color=GRID, lw=.8)
            for s in ("top", "right"): ax.spines[s].set_visible(False)
            ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k"))
            ax.set_title(f"RRR {rr} (TP {tp} / SL {sl} ticků) · {DIRNAME[mode][d]}", loc="left", fontsize=10, color=INK)
    import matplotlib.dates as mdates
    for ax in axes[-1]:
        ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0, 0].legend(frameon=False, loc="lower left", fontsize=9, ncol=2)
    axes[0, 0].set_ylim(ymin * 1.05, ymax * 1.15)
    fig.suptitle(("MOMENTUM – stop order ve směru pohybu od open" if mode == "momentum"
                  else "FADE – limitka proti pohybu od open") +
                 " · equity po nákladech 0,5 b./obchod, 1 ES, 07/2016–07/2026", x=0.01, ha="left", color=INK, fontsize=13)
    fig.tight_layout(rect=(0, 0, 0.97, 0.97)); fig.subplots_adjust(wspace=0.32); fig.savefig(f"{D}/equity_{mode}.png", dpi=130); plt.close(fig)
print("hotovo")
