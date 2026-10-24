"""Static PNG charts of the RRR matrix (out/charts/), for Google Drive and the repository."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LogNorm, TwoSlopeNorm

OUT = os.environ.get("CHART_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "charts"))
D = "/tmp/claude-0/dash"
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
CMAP = LinearSegmentedColormap.from_list("rg", ["#b2182b", "#f7f7f7", "#1a7f37"])
HOR = {"intraday": "intraday", "5D": "5 dní", "20D": "20 dní"}
plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "figure.dpi": int(os.environ.get("DPI", "130"))})


def heat(mode, metric, fname, title, fmt="{:+.3f}"):
    a = pd.read_csv(os.path.join(SRC, "A_grand.csv"))
    a = a[a["mode"] == mode]
    if metric == "winx":
        a = a.assign(v=a.win - a.nahodna_win)
    else:
        a = a.assign(v=a[metric])
    lim = max(0.02, float(np.nanquantile(np.abs(a.v), 0.95)))
    fig, axs = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    for i, side in enumerate(("long", "short")):
        for j, h in enumerate(HOR):
            x = a[(a.smer == side) & (a.horizont == h)].pivot(index="SL", columns="RRR", values="v")
            ax = axs[i, j]
            im = ax.imshow(x.values, cmap=CMAP, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
            ax.set_xticks(range(len(x.columns)), [f"1:{c:g}" for c in x.columns])
            ax.set_yticks(range(len(x.index)), [f"{s:g}" for s in x.index])
            for (yy, xx), v in np.ndenumerate(x.values):
                if np.isfinite(v):
                    ax.text(xx, yy, fmt.format(v), ha="center", va="center", fontsize=6.5)
            ax.set_title(f"{side} · {HOR[h]}")
            ax.set_xlabel("RRR"); ax.set_ylabel("SL (body)" if mode == "points" else "SL (× ATR)")
    fig.colorbar(im, ax=axs, shrink=0.6)
    fig.suptitle(title, fontsize=12)
    fig.savefig(os.path.join(OUT, fname)); plt.close(fig)


def equity():
    e = pd.read_csv(os.path.join(D, "equity.csv")); e["tyden"] = pd.to_datetime(e.tyden)
    fig, ax = plt.subplots(figsize=(13, 6.5), constrained_layout=True)
    for name, g in e.groupby("strategie"):
        bh = name.startswith("Buy")
        ax.plot(g.tyden, g.equity, lw=2.6 if bh else 1.6, color="black" if bh else None,
                label=name.replace("Buy & hold ES", "Buy & hold S&P 500") + f": {g.equity.iloc[-1]:.2f}×")
    ax.set_yscale("log"); ax.axvline(pd.Timestamp("2019-01-01"), ls="--", color="grey")
    ax.text(pd.Timestamp("2019-02-01"), ax.get_ylim()[1] * 0.8, "test od 2019 →", color="grey")
    ax.set_yticks([0.1, 0.25, 0.5, 1, 2, 4, 6], ["0,1×", "0,25×", "0,5×", "1×", "2×", "4×", "6×"])
    ax.grid(alpha=.3); ax.legend(loc="lower left", fontsize=8)
    ax.set_title("Equity křivky 2011–2026: riziko 1 % na obchod, jedna pozice najednou, proti buy & hold S&P 500")
    fig.savefig(os.path.join(OUT, "equity.png")); plt.close(fig)


def hours():
    h = pd.read_csv(os.path.join(D, "hours.csv"))
    combos = h.kombinace.unique()
    fig, axs = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    for ax, c in zip(axs.ravel(), combos):
        g = h[h.kombinace == c]
        x = np.arange(len(g)); w = 0.4
        ax.bar(x - w / 2, g.R_2011_18, w, color="#bbbbbb", label="2011–18 (výběr)")
        ax.bar(x + w / 2, g.R_2019_26, w, color="#2b6cb0", label="2019–26 (test)")
        ax.set_xticks(x, g.hodina); ax.axhline(0, color="black", lw=.8)
        ax.set_title(c); ax.set_xlabel("hodina vstupu (ET)"); ax.set_ylabel("R/obchod"); ax.grid(axis="y", alpha=.3)
    axs[0, 0].legend()
    fig.suptitle("Výsledek podle hodiny vstupu", fontsize=12)
    fig.savefig(os.path.join(OUT, "hodiny.png")); plt.close(fig)


def streaks():
    s = pd.read_csv(os.path.join(SRC, "C_streaks.csv"))
    s = s[s.smer == "long"]
    fig, axs = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    for j, h in enumerate(HOR):
        for i, (col, lab) in enumerate((("max_serie", "skutečná max. série"), ("iid_max_serie", "max. série při stejné win % náhodně"))):
            x = s[s.horizont == h].pivot(index="SL", columns="RRR", values=col)
            ax = axs[i, j]
            im = ax.imshow(x.values, cmap="magma_r", norm=LogNorm(1, 6000), aspect="auto")
            ax.set_xticks(range(len(x.columns)), [f"1:{c:g}" for c in x.columns])
            ax.set_yticks(range(len(x.index)), [f"{v:g}" for v in x.index])
            for (yy, xx), v in np.ndenumerate(x.values):
                ax.text(xx, yy, f"{v:.0f}", ha="center", va="center", fontsize=6.5, color="white" if v > 300 else "black")
            ax.set_title(f"{HOR[h]} · {lab}"); ax.set_xlabel("RRR"); ax.set_ylabel("SL (body)")
    fig.colorbar(im, ax=axs, shrink=0.6, label="počet ztrát v řadě")
    fig.suptitle("Nejdelší série ztrát (long, jedna pozice najednou, 2011–2026)", fontsize=12)
    fig.savefig(os.path.join(OUT, "serie_ztrat.png")); plt.close(fig)


def stophunt():
    f = pd.read_csv(os.path.join(D, "stophunt.csv"))
    f["lab"] = f.level + " · " + f.smer + " · " + f.varianta
    fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
    y = np.arange(len(f))
    ax.hlines(y, f.R_nahodny, f.R, color="#cccccc", lw=3)
    ax.scatter(f.R_nahodny, y, color="#999999", label="náhodný vstup po signálu", zorder=3)
    ax.scatter(f.R, y, color="#2b6cb0", label="vstup po sweepu", zorder=3)
    ax.set_yticks(y, f.lab); ax.axvline(0, color="black", lw=.8); ax.grid(axis="x", alpha=.3)
    ax.set_xlabel("R/obchod (průměr přes SL 6–100 b. × RRR 1–25)"); ax.legend()
    ax.set_title("Stop-hunt hypotéza: vstup po vybrání stopů proti náhodnému vstupu")
    fig.savefig(os.path.join(OUT, "stophunt.png")); plt.close(fig)


def winrate_curve():
    a = pd.read_csv(os.path.join(SRC, "A_grand.csv"))
    a = a[(a["mode"] == "points") & (a.horizont == "20D") & (a.smer == "long")]
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    rr = np.linspace(1, 25, 100)
    ax.plot(rr, 1 / (1 + rr), color="black", lw=2, label="náhodná cena 1/(1+RRR)")
    for s in (6, 10, 20, 40, 100):
        g = a[a.SL == s]
        ax.plot(g.RRR, g.win, marker="o", label=f"SL {s} b. (skutečná)")
    ax.set_xlabel("RRR"); ax.set_ylabel("win rate"); ax.grid(alpha=.3); ax.legend()
    ax.set_title("Win rate long 20 dní proti náhodné ceně (rozdíl = obchody uzavřené časem a drift)")
    fig.savefig(os.path.join(OUT, "winrate_vs_nahoda.png")); plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    heat("points", "R", "heat_R_body.png", "R/obchod po nákladech: SL v bodech × RRR (ES 2011–2026, vstup každou hodinu)")
    heat("atr", "R", "heat_R_atr.png", "R/obchod po nákladech: SL v ATR timeframe × RRR (ES 2011–2026)")
    heat("points", "R_2019_26", "heat_R_body_2019_26.png", "R/obchod 2019–26 (mimo výběrové období): SL v bodech × RRR")
    heat("points", "winx", "heat_win_minus_nahoda.png", "Win rate − náhodná win rate 1/(1+RRR): SL v bodech × RRR", fmt="{:+.2f}")
    equity(); hours(); streaks(); stophunt(); winrate_curve()
    print(sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
