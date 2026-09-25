"""RRR 1,5 : 1 na open + X: long i short, s výstupem v 15:55 i bez, SL 2–30 b.
Obchody z emulace studie (main.cpp, Exit Mode RRR + fixed SL), náklady 0,5 b., 1 ES.
Počítá i nutnou úspěšnost (break-even s náklady a pro t ≥ 2 při 1 000 obchodech).

python sierra/test_harness/rrr15.py <složka s t_X_K_SL_1.5_DIR.csv> <random.csv> <výstupní složka>
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates

GRID, RAND, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
COST, PV, R = 0.5, 50.0, 1.5
SLS = [2, 3, 5, 7.5, 10, 15, 20, 30]
RAMP = ["#b7d3f6", "#86b6ef", "#5598e7", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
INK, SEC, MUTED, GRIDC, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5})
c = lambda v, d=1: f"{v:.{d}f}".replace(".", ",").replace("-", "−")
m = lambda v: ("−" if v < 0 else "+") + "$" + f"{abs(v)/1000:.1f}".replace(".", ",") + "k"
g = lambda v: f"{v:g}".replace(".", ",")

def load(X, K, SL, D):
    t = pd.read_csv(os.path.join(GRID, f"t_{X}_{K}_{SL:g}_1.5_{D}.csv"))
    t["pnl"] = ((t.exit - t.entry) * t.dir - COST) * PV
    t["xts"] = pd.to_datetime(t.xd.astype(str)) + pd.to_timedelta(t.xt, unit="s")
    return t

def stats(t):
    p = t.pnl.values / PV; eq = np.cumsum(p) * PV
    s = b = 0
    for v in p:
        s = 0 if v > 0 else s + 1; b = max(b, s)
    return dict(n=len(p), tp=(t.why == "T").mean() * 100, sl=(t.why == "S").mean() * 100,
                win=(p > 0).mean() * 100, usd=p.sum() * PV, ptt=p.mean(),
                t=p.mean() / p.std(ddof=1) * np.sqrt(len(p)), dd=(eq - np.maximum.accumulate(eq)).min(), streak=b)

def need(SL, t_req=0.0, N=1000):
    """Úspěšnost (TP proti SL), při které má obchod nulový zisk (t_req = 0) nebo t ≥ t_req při N obchodech."""
    W, L = SL * R - COST, -(SL + COST)
    if t_req == 0: return -L / (W - L) * 100
    for p in np.arange(0, 1, 1e-4):
        mu = p * W + (1 - p) * L; sd = np.sqrt(p * (1 - p)) * (W - L)
        if sd > 0 and mu / sd * np.sqrt(N) >= t_req: return p * 100

rows = []
for X in (10, 15):
    fig, axes = plt.subplots(2, 2, figsize=(19, 9.5), sharex=True, sharey=True,
                             gridspec_kw={"hspace": 0.25, "wspace": 0.42})
    fig.patch.set_facecolor(SURF)
    for r_i, K in enumerate((0, 1)):
        for c_i, (D, smer) in enumerate(((1, "long"), (2, "short"))):
            ax = axes[r_i, c_i]
            ax.set_facecolor(SURF); ax.grid(axis="y", color=GRIDC, lw=0.8); ax.set_axisbelow(True)
            for sp in ("top", "right"): ax.spines[sp].set_visible(False)
            for sp in ("left", "bottom"): ax.spines[sp].set_color(GRIDC)
            ax.tick_params(colors=MUTED); ax.axhline(0, color=MUTED, lw=0.8)
            for SL, col in zip(SLS, RAMP):
                t = load(X, K, SL, D); st = stats(t)
                rows.append(dict(X=X, kill="Yes" if K else "No", smer=smer, SL=SL, TPb=SL * R, **st))
                eq = t.set_index("xts").pnl.cumsum() / 1000
                ax.plot(eq.index, eq.values, color=col, lw=1.4,
                        label=f"SL {g(SL)} / TP {g(SL*R)} b.: {m(st['usd'])}")
            lvl = f"open + {X}" if smer == "long" else f"open − {X}"
            ax.set_title(f"{smer.upper()} na {lvl} · {'Kill = Yes: výstup 15:55' if K else 'Kill = No: drží do TP/SL'}",
                         loc="left", color=INK, fontweight="bold", fontsize=10)
            ax.legend(frameon=False, labelcolor=SEC, fontsize=8.5, loc="upper left", bbox_to_anchor=(1.0, 1.0))
            if c_i == 0: ax.set_ylabel("Kumulativní zisk (tis. $, 1 ES)", color=SEC)
    axes[-1, 0].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(f"RRR 1,5 : 1 · průraz open ± {X} b., max. 1 obchod denně · ES 07/2016–07/2026, náklady 0,5 b./obchod",
                 x=0.125, ha="left", color=INK, fontsize=13, fontweight="bold", y=0.96)
    fig.savefig(os.path.join(OUT, f"equity_open{X}.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)

S = pd.DataFrame(rows); rnd = pd.read_csv(RAND)
S.round(3).to_csv(os.path.join(OUT, "souhrn.csv"), index=False)
L = ["# RRR 1,5 : 1 na open ± X: výsledky a nutná úspěšnost\n",
     "Obchody ze studie `sierra/Lukacino_OpenX_Range_RRR.cpp` v emulaci Replay: Entry Mode Open +/- X (Breakout: "
     "long na open + X, short na open − X), Exit Mode RRR + fixed SL, RRR 1,5, vstup 9:30–15:00, max. 1 obchod denně, "
     "1 ES, náklady 0,5 b. na obchod, ES 07/2016–07/2026. Grafy: `equity_open10.png`, `equity_open15.png`. "
     "Data: `souhrn.csv`, `nahodny_long.csv`.\n",
     "## Nutná úspěšnost\n",
     "Nutná úspěšnost = (SL + náklady) / (SL × 2,5). Bez nákladů 40,0 %. „Prokazatelná hrana“ = úspěšnost, "
     "při které 1 000 obchodů dá t ≥ 2. Skutečná úspěšnost = podíl TP mezi obchody, které skončily na TP nebo SL "
     "(long, Kill = No). Náhodný long = vstup v náhodném čase 9:30–15:00, drží do TP/SL, 10 opakování.\n",
     "| SL / TP (b.) | Break-even s náklady | Prokazatelná hrana | open+10 | open+15 | náhodný long | Náhodný long: zisk (medián) |",
     "|---|---|---|---|---|---|---|"]
for SL in SLS:
    a = S[(S.smer == "long") & (S.kill == "No") & (S.SL == SL)]
    tp_share = lambda r: r.tp / (r.tp + r.sl) * 100
    rr = rnd[rnd.SL == SL].iloc[0]
    L.append(f"| {g(SL)} / {g(SL*R)} | **{c(need(SL))} %** | {c(need(SL, 2))} % | {c(tp_share(a[a.X==10].iloc[0]))} % | "
             f"{c(tp_share(a[a.X==15].iloc[0]))} % | {c(rr.win)} % | {m(rr.usd_med)} |")
for smer in ("long", "short"):
    for K in ("No", "Yes"):
        L += [f"\n## {smer.upper()}, Kill at Session End = {K}\n",
              "| X | SL / TP | Obchodů | TP | SL | Konec dne | Ziskových | Čistý zisk | b./obchod | t | Max. DD | Nejdelší série ztrát |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in S[(S.smer == smer) & (S.kill == K)].sort_values(["X", "SL"]).iterrows():
            L.append(f"| {r.X} | {g(r.SL)} / {g(r.TPb)} | {r.n} | {c(r.tp)} % | {c(r.sl)} % | {c(100-r.tp-r.sl)} % | "
                     f"{c(r.win)} % | {m(r.usd)} | {c(r.ptt, 2)} | {c(r.t, 2)} | {m(r.dd)} | {r.streak} |")
open(os.path.join(OUT, "PREHLED.md"), "w").write("\n".join(L) + "\n")
print(S[["X", "kill", "smer", "SL", "n", "tp", "sl", "win", "usd", "t", "dd", "streak"]].round(1).to_string(index=False))
