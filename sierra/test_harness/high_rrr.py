"""Vysoké RRR (10, 15, 20 : 1): long/short na open + X, max. 1 obchod denně, různé SL.
Obchody z emulace studie (main.cpp, Exit Mode RRR + fixed SL), náklady 0,5 b., 1 ES.

python sierra/test_harness/high_rrr.py <složka s t_X_K_SL_RRR_DIR.csv> <random.csv> <výstupní složka>
"""
import sys, os, glob
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates

GRID, RAND, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
COST, PV = 0.5, 50.0
SLS = [2, 3, 5, 7.5, 10, 15]
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]   # SL malý -> velký
INK, SEC, MUTED, GRIDC, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5})
fmtk = lambda v: (f"{v/1000:+,.1f}k").replace(".", ",").replace("-", "−")

def load(X, K, SL, R, D):
    f = os.path.join(GRID, f"t_{X}_{K}_{SL:g}_{R}_{D}.csv")
    t = pd.read_csv(f)
    t["pnl"] = ((t.exit - t.entry) * t.dir - COST) * PV
    t["xts"] = pd.to_datetime(t.xd.astype(str)) + pd.to_timedelta(t.xt, unit="s")
    return t

def stats(t, R):
    p = t.pnl.values / PV; eq = np.cumsum(p) * PV
    s = b = 0
    for v in p:
        s = 0 if v > 0 else s + 1; b = max(b, s)
    return dict(n=len(p), tp=(t.why == "T").mean() * 100, win=(p > 0).mean() * 100, be=100 / (R + 1),
                usd=p.sum() * PV, ptt=p.mean(), t=p.mean() / p.std(ddof=1) * np.sqrt(len(p)),
                dd=(eq - np.maximum.accumulate(eq)).min(), streak=b)

rows = []
for X in (10, 15):
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.6), sharex=True, sharey=True,
                             gridspec_kw={"hspace": 0.28, "wspace": 0.06})
    fig.patch.set_facecolor(SURF)
    for r_i, K in enumerate((0, 1)):
        for c_i, R in enumerate((10, 15, 20)):
            ax = axes[r_i, c_i]
            ax.set_facecolor(SURF); ax.grid(axis="y", color=GRIDC, lw=0.8); ax.set_axisbelow(True)
            for sp in ("top", "right"): ax.spines[sp].set_visible(False)
            for sp in ("left", "bottom"): ax.spines[sp].set_color(GRIDC)
            ax.tick_params(colors=MUTED)
            ax.axhline(0, color=MUTED, lw=0.8)
            for SL, col in zip(SLS, RAMP):
                t = load(X, K, SL, R, 1)
                st = stats(t, R); rows.append(dict(X=X, kill="Yes" if K else "No", SL=SL, RRR=R, smer="long", **st))
                eq = t.set_index("xts").pnl.cumsum() / 1000
                ax.plot(eq.index, eq.values, color=col, lw=1.4, label=f"SL {SL:g} / TP {SL*R:g} b.: {fmtk(st['usd'])}")
                ts = load(X, K, SL, R, 2)
                rows.append(dict(X=X, kill="Yes" if K else "No", SL=SL, RRR=R, smer="short", **stats(ts, R)))
            ax.set_title(f"RRR {R}:1 · {'Kill = Yes: výstup 15:55' if K else 'Kill = No: drží do TP/SL'}",
                         loc="left", color=INK, fontweight="bold", fontsize=10)
            ax.legend(frameon=False, labelcolor=SEC, fontsize=8, loc="upper left")
            if c_i == 0: ax.set_ylabel("Kumulativní zisk (tis. $, 1 ES)", color=SEC)
    axes[-1, 0].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(f"Long na open + {X} b., max. 1 obchod denně, TP = RRR × SL · ES 07/2016–07/2026, náklady 0,5 b./obchod",
                 x=0.125, ha="left", color=INK, fontsize=13, fontweight="bold", y=0.96)
    fig.savefig(os.path.join(OUT, f"equity_open{X}.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)

S = pd.DataFrame(rows)
rnd = pd.read_csv(RAND)
S.round(3).to_csv(os.path.join(OUT, "souhrn.csv"), index=False)

c = lambda v, d=1: f"{v:.{d}f}".replace(".", ",").replace("-", "−")
m = lambda v: ("−" if v < 0 else "") + "$" + f"{abs(v)/1000:.1f}".replace(".", ",") + "k"
g = lambda v: f"{v:g}".replace(".", ",")
L = ["# Vysoké RRR (10, 15, 20 : 1) na open + X\n",
     "Obchody ze studie `sierra/Lukacino_OpenX_Range_RRR.cpp` v emulaci Replay: Entry Mode Open +/- X (Breakout), "
     "Exit Mode RRR + fixed SL, vstup 9:30–15:00, max. 1 obchod denně, 1 ES, náklady 0,5 b. na obchod. "
     "ES 07/2016–07/2026. Grafy: `equity_open10.png`, `equity_open15.png`. Všechna čísla: `souhrn.csv`.\n",
     "**Break-even úspěšnost** bez nákladů = 1 / (RRR + 1): 9,1 % při 10:1, 6,2 % při 15:1, 4,8 % při 20:1. "
     "U náhodné ceny vychází TP % právě tak.\n"]
for smer in ("long", "short"):
    for K in ("No", "Yes"):
        L += [f"\n## {smer.upper()}, Kill at Session End = {K}\n",
              "| X | RRR | SL / TP | Obchodů | TP zasažen | Break-even | Čistý zisk | b./obchod | t | Max. DD | Nejdelší série ztrát |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in S[(S.smer == smer) & (S.kill == K)].sort_values(["X", "RRR", "SL"]).iterrows():
            L.append(f"| {r.X} | {r.RRR}:1 | {g(r.SL)} / {g(r.SL*r.RRR)} | {r.n} | {c(r.tp)} % | {c(r.be)} % | "
                     f"{m(r.usd)} | {c(r.ptt, 2)} | {c(r.t, 2)} | {m(r.dd)} | {r.streak} |")
L += ["\n## Kontrola: náhodný long se stejným SL a RRR (drží do TP/SL)\n",
      "Vstup v náhodném čase 9:30–15:00, max. 1 pozice, 10 opakování. Srovnání s long open + X, Kill = No.\n",
      "| SL / RRR | Náhodný long: úspěšnost | Náhodný long: zisk (medián, 10.–90. perc.) | open+10 | open+15 |",
      "|---|---|---|---|---|"]
for _, r in rnd.iterrows():
    a = S[(S.smer == "long") & (S.kill == "No") & (S.SL == r.SL) & (S.RRR == r.RRR)]
    v10 = a[a.X == 10].usd.iloc[0]; v15 = a[a.X == 15].usd.iloc[0]
    L.append(f"| {g(r.SL)} b. / {int(r.RRR)}:1 | {c(r.win)} % | {m(r.usd_med)} ({m(r.usd_lo)} až {m(r.usd_hi)}) | "
             f"{m(v10)} | {m(v15)} |")
open(os.path.join(OUT, "PREHLED.md"), "w").write("\n".join(L) + "\n")
print("ok")
