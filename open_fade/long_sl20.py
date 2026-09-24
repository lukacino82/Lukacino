"""Jen LONG, SL 20 b., RRR 2:1 (TP 40) a 3:1 (TP 60); vstup na open+X (stop) a open−X (limit).
Výstup: souhrn CSV, heatmapa, equity křivky."""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
sys.path.insert(0, os.path.dirname(__file__))
from open_fade import load_bars, simulate_day, Params

DATA = sys.argv[1]; OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/open_fade/long_sl20"
os.makedirs(OUT, exist_ok=True)
COST, PV, SL = 0.5, 50.0, 80                      # SL 80 ticků = 20 bodů
RRR = {"2:1": 160, "3:1": 240}                    # TP v tickách
XS = [10, 15, 20, 30, 40]
ENTRY = {"momentum": "LONG na open + X (stop order)", "fade": "LONG na open − X (limitka)"}
df = load_bars(DATA); t = df.index.time
rth = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
days = [(pd.Timestamp(d), (g.open.values, g.high.values, g.low.values, g.close.values, g.index.time))
        for d, g in rth.groupby(rth.index.date) if g.index[-1].time() >= pd.Timestamp("15:45").time()]
rows, trades = [], []
for mode in ENTRY:
    for rr, tp in RRR.items():
        for x in XS:
            p = Params(level=x, tp_ticks=tp, sl_ticks=SL, mode=mode)
            res = []
            for d, a in days:
                r = simulate_day(*a, p, 1)
                if r: res.append((d, r[0], r[1] - COST))
            tr = pd.DataFrame(res, columns=["date", "result", "pts"]); tr["mode"], tr["rrr"], tr["X"] = mode, rr, x
            trades.append(tr)
            p_ = tr.pts; eq = (p_ * PV).cumsum(); dec = tr[tr.result != "EOD"]
            yrs = p_.groupby(tr.date.dt.year).sum()
            rows.append(dict(vstup=mode, RRR=rr, TP_b=tp / 4, SL_b=SL / 4, X=x, dni=len(days), obchodu=len(tr),
                             vstup_pct=100 * len(tr) / len(days), TP=int((tr.result == "TP").sum()),
                             SL=int((tr.result == "SL").sum()), EOD=int((tr.result == "EOD").sum()),
                             TP_pct=100 * (dec.result == "TP").mean(), breakeven=100 * SL / (SL + tp),
                             b_obchod=p_.mean(), t=p_.mean() / p_.std() * np.sqrt(len(p_)), usd=eq.iloc[-1],
                             maxdd=(eq - eq.cummax()).min(), kladne_roky=f"{(yrs > 0).sum()}/{len(yrs)}"))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/souhrn.csv", index=False)
T = pd.concat(trades)
pd.set_option("display.width", 220); print(R.round(2).to_string(index=False))

INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
XCOL = {10: "#2a78d6", 15: "#eb6834", 20: "#1baf7a", 30: "#e87ba4", 40: "#eda100"}
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "figure.facecolor": SURF, "axes.facecolor": SURF})
usd = lambda v: ("−" if v < 0 else "+") + f"${abs(v)/1000:,.1f}k"
# ---------- heatmapa ----------
cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"]); lim = R.usd.abs().max()
fig, axes = plt.subplots(1, 2, figsize=(13, 6.4))
for ax, mode in zip(axes, ENTRY):
    sub = R[R.vstup == mode]
    M = sub.pivot(index="X", columns="RRR", values="usd").loc[XS, list(RRR)]
    ax.imshow(M.values, cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    for i, x in enumerate(XS):
        for j, rr in enumerate(RRR):
            row = sub[(sub.X == x) & (sub.RRR == rr)].iloc[0]
            ax.text(j, i - 0.2, usd(row.usd), ha="center", va="center", fontsize=11, weight="bold", color=INK)
            ax.text(j, i + 0.12, f"t {row.t:+.1f} · {row.obchodu} obch.", ha="center", va="center", fontsize=8.5, color=MUTED)
            ax.text(j, i + 0.33, f"TP {row.TP} · SL {row.SL} · 16:00 {row.EOD}", ha="center", va="center", fontsize=8.5, color=MUTED)
    ax.set_xticks(range(len(RRR)), [f"RRR {k}\nTP {v//4} b. / SL 20 b." for k, v in RRR.items()])
    ax.set_yticks(range(len(XS)), [f"X = {x}" for x in XS])
    ax.set_xticks(np.arange(-.5, len(RRR)), minor=True); ax.set_yticks(np.arange(-.5, len(XS)), minor=True)
    ax.grid(which="minor", color=SURF, lw=3); ax.tick_params(which="minor", length=0)
    for s in ax.spines.values(): s.set_visible(False)
    ax.set_title(ENTRY[mode], loc="left", color=INK, fontsize=11.5)
fig.suptitle("ES jen LONG, SL 20 b.: čistý výsledek 07/2016–07/2026 po nákladech 0,5 b./obchod (1 ES)\n"
             "modrá = zisk · červená = ztráta · spodní řádek = kolik obchodů skončilo na TP, SL a v 16:00", x=0.01, ha="left", color=INK, fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.9)); fig.savefig(f"{OUT}/heatmapa.png", dpi=150); plt.close(fig)
# ---------- equity ----------
fig, axes = plt.subplots(2, 2, figsize=(15, 9.5), sharex=True, sharey=True)
curves = {}
for (mode, rr), g in T.groupby(["mode", "rrr"]):
    for x in XS:
        s = g[g.X == x]; curves[(mode, rr, x)] = (s.pts * PV).groupby(s.date).sum().cumsum()
lo = min(c.min() for c in curves.values()); hi = max(c.max() for c in curves.values()); gap = (hi - lo) * 0.045
for r, mode in enumerate(ENTRY):
    for c, rr in enumerate(RRR):
        ax = axes[r, c]; ends = []
        for x in XS:
            eq = curves[(mode, rr, x)]; ax.plot(eq.index, eq.values, color=XCOL[x], lw=1.7, label=f"X = {x}")
            ends.append([eq.iloc[-1], x])
        ends.sort(); ys = [e[0] for e in ends]
        for k in range(1, len(ys)): ys[k] = max(ys[k], ys[k - 1] + gap)
        xend = T.date.max()
        for (v, x), yl in zip(ends, ys):
            ax.plot([xend], [yl], marker="s", ms=4, color=XCOL[x], clip_on=False)
            ax.annotate(f"X={x}: {usd(v)}", (xend, yl), xytext=(5, 0), textcoords="offset points", fontsize=8.5, color=INK, va="center")
        ax.axhline(0, color=MUTED, lw=1); ax.grid(axis="y", color=GRID, lw=.8)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k"))
        ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_title(f"{ENTRY[mode]} · RRR {rr} (TP {RRR[rr]//4} b. / SL 20 b.)", loc="left", fontsize=10.5, color=INK)
axes[0, 0].legend(frameon=False, loc="upper left", fontsize=9, ncol=3); axes[0, 0].set_ylim(lo * 1.1, hi * 1.25)
fig.suptitle("ES jen LONG, SL 20 b. · equity po nákladech 0,5 b./obchod, 1 ES, 07/2016–07/2026",
             x=0.01, ha="left", color=INK, fontsize=12.5)
fig.tight_layout(rect=(0, 0, 0.95, 0.96)); fig.subplots_adjust(wspace=0.25)
fig.savefig(f"{OUT}/equity.png", dpi=140); plt.close(fig)
