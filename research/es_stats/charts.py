"""Charts for blocks 1-6 (statistics, delta, VWAP, profile, money management, patterns) -> es_stats/out/charts."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

R = "/home/user/Lukacino/research"
OUTD = os.path.join(R, "es_stats", "out", "charts")
INK = "#1f2328"; MUTED = "#6e7781"; GRID = "#d8dee4"; BLUE = "#1d4ed8"; RED = "#c2410c"; GREEN = "#15803d"; AMBER = "#f59e0b"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold"})
WD = ["Po", "Ut", "St", "Ct", "Pa"]
WDL = ["Po", "Út", "St", "Čt", "Pá"]


def save(fig, name):
    os.makedirs(OUTD, exist_ok=True)
    fig.savefig(os.path.join(OUTD, name), dpi=130, bbox_inches="tight", facecolor="white"); plt.close(fig)


def heat(ax, p, title, fmt, cmap, vmin=None, vmax=None):
    im = ax.imshow(p.to_numpy(), aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_yticks(range(p.shape[0])); ax.set_yticklabels(WDL)
    ax.set_xticks(range(p.shape[1])); ax.set_xticklabels(p.columns)
    for i in range(p.shape[0]):
        for j in range(p.shape[1]):
            ax.text(j, i, fmt.format(p.iloc[i, j]), ha="center", va="center", fontsize=6.5, color=INK)
    ax.set_title(title); ax.grid(False); ax.set_xlabel("hodina ET (začátek)")
    return im


def hours():
    A = pd.read_csv(os.path.join(R, "es_stats/out/A2_den_hodina.csv"))
    A = A[A.den.isin(WD) & (A.hodina != 17)]
    fig, axs = plt.subplots(2, 1, figsize=(15, 8), gridspec_kw=dict(hspace=0.45))
    p = A.pivot(index="den", columns="hodina", values="rozpeti_pct").reindex(WD)
    im = heat(axs[0], p, "Průměrné rozpětí hodiny (% ceny) – den × hodina", "{:.2f}", "Blues")
    fig.colorbar(im, ax=axs[0], shrink=0.8)
    p = A.pivot(index="den", columns="hodina", values="vynos_pct").reindex(WD)
    im = heat(axs[1], p * 100, "Průměrný výnos hodiny (bazické body, 0,01 %) – modrá růst, červená pokles", "{:.1f}", "RdBu", -3, 3)
    fig.colorbar(im, ax=axs[1], shrink=0.8)
    save(fig, "hodiny_dny.png")


def weekdays():
    B = pd.read_csv(os.path.join(R, "es_stats/out/B1_dny.csv")).set_index("den").reindex(WD)
    S = pd.read_csv(os.path.join(R, "es_stats/out/B4_dny_signifikance.csv"))
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    axs[0].bar(WDL, B.vynos_pct, color=BLUE); axs[0].set_title("Průměrný výnos dne (%)")
    for k, d in enumerate(WD):
        t = S[(S.skupina == d) & (S.test == "vynos dne %")].t.iloc[0]
        axs[0].text(k, B.vynos_pct.iloc[k], f"t {t:.1f}", ha="center", va="bottom", fontsize=8, color=MUTED)
    axs[1].bar(WDL, B.vyprodej_10pct * 100, color=RED); axs[1].axhline(10, color=INK, ls="--", lw=1)
    axs[1].set_title("Podíl výprodejů (nejhorších 10 % dnů roku), %")
    axs[2].bar(WDL, B.rozpeti_pct, color=AMBER); axs[2].set_title("Průměrné rozpětí RTH (%) – pondělí nejmenší")
    save(fig, "dny_v_tydnu.png")


def drawdowns():
    W = pd.read_csv(os.path.join(R, "es_stats/out/C_tydny.csv")); W["rok"] = W.obdobi.str[:4].astype(int)
    Y = pd.read_csv(os.path.join(R, "es_stats/out/C_roky.csv"))
    fig, axs = plt.subplots(1, 2, figsize=(15, 4.6))
    data = [W[W.rok == y].max_propad_pct.to_numpy() for y in sorted(W.rok.unique())]
    axs[0].boxplot(data, tick_labels=sorted(W.rok.unique()), showfliers=True, flierprops=dict(markersize=3))
    axs[0].set_title("Největší propad uvnitř týdne (%) podle roku"); axs[0].tick_params(axis="x", rotation=45)
    x = np.arange(len(Y))
    axs[1].bar(x - 0.2, Y.vynos_pct, 0.4, color=GREEN, label="výnos roku %")
    axs[1].bar(x + 0.2, Y.max_propad_pct, 0.4, color=RED, label="max propad v roce %")
    axs[1].set_xticks(x); axs[1].set_xticklabels(Y.obdobi, rotation=45); axs[1].axhline(0, color=INK, lw=0.8)
    axs[1].set_title("Roční výnos vs největší propad v roce"); axs[1].legend(frameon=False)
    save(fig, "propady.png")


def mm():
    E = pd.read_parquet(os.path.join(R, "money_mgmt/out/equity.parquet"))
    H = pd.read_csv(os.path.join(R, "money_mgmt/out/A_historie_2010_2026.csv"))
    fig, axs = plt.subplots(1, 2, figsize=(15, 5))
    show = {"buy & hold 1x": INK, "buy & hold 2x": MUTED, "martingale (2x po ztratovem tydnu)": RED,
            "D'Alembert (+0.5x po ztrate, -0.5x po zisku)": AMBER, "pyramidovani: +0.5x za kazdych 5 % pod maximem": BLUE,
            "pocitani karet: 2x pri signalu (RSI2<10 nebo pod W-VWAP -1SD)": GREEN, "Kelly (plny)": "#7c3aed"}
    for k, c in show.items():
        axs[0].plot(E.index, E[k], color=c, lw=1.2, label=k)
    axs[0].set_yscale("log"); axs[0].set_title("Equity (log), start = 1"); axs[0].legend(frameon=False, fontsize=7)
    bh = H[H.pravidlo.str.startswith("buy & hold")]
    lev = np.linspace(0.5, 3.2, 30)
    axs[1].plot(-bh.maxDD * 100, bh.CAGR * 100, "o-", color=INK, label="buy & hold 1x / 2x / 3x")
    o = H[~H.pravidlo.str.startswith("buy & hold")]
    axs[1].scatter(-o.maxDD * 100, o.CAGR * 100, color=BLUE)
    for _, r in o.iterrows():
        axs[1].annotate(r.pravidlo.split(":")[0].split("(")[0][:22], (-r.maxDD * 100, r.CAGR * 100), fontsize=7, color=MUTED)
    axs[1].set_xlabel("max propad %"); axs[1].set_ylabel("CAGR %")
    axs[1].set_title("Výnos vs propad: nad černou čarou = lepší než páka na B&H"); axs[1].legend(frameon=False)
    save(fig, "money_management.png")


def delta_vwap():
    B = pd.read_csv(os.path.join(R, "delta_vwap/out/B_cd_extremy.csv"))
    b = B[(B.typ == "kontrakty") & (B.sazka == "pokracovani") & (B.horizont == "close")].sort_values("uroven")
    D = pd.read_csv(os.path.join(R, "delta_vwap/out/D_vwap_fade_sd.csv"))
    d = D[(D.rezim == "vse") & (D.vwap == "denni VWAP (18:00)")]
    fig, axs = plt.subplots(1, 2, figsize=(15, 4.4))
    axs[0].bar([f"{int(x / 1000)}k" for x in b.uroven], b.excess_atr, color=[GREEN if x > 0 else RED for x in b.uroven])
    for k, (e, t) in enumerate(zip(b.excess_atr, b.t)):
        axs[0].text(k, e, f"t {t:.1f}", ha="center", va="bottom" if e >= 0 else "top", fontsize=7, color=MUTED)
    axs[0].axhline(0, color=INK, lw=0.8); axs[0].set_xlabel("první dosažení kumulativní delty v daném dni (kontrakty)")
    axs[0].set_title("Pohyb ve směru delty do závěru dne (ATR, proti stejnému času)")
    lab = [f"{'−' if s.startswith('long') else '+'}{k}SD → {c}" for s, k, c in zip(d.strana, d.SD, d.cil)]
    x = np.arange(len(d))
    axs[1].bar(x - 0.2, d.win_uzavrene * 100, 0.4, color=BLUE, label="úspěšnost fade")
    axs[1].bar(x + 0.2, d.nahodna_win * 100, 0.4, color=MUTED, label="náhodná cena")
    axs[1].set_xticks(x); axs[1].set_xticklabels(lab, rotation=40, ha="right", fontsize=8)
    axs[1].set_title("Fade pásem denního VWAP: úspěšnost vs náhoda (%)"); axs[1].legend(frameon=False)
    save(fig, "delta_vwap.png")


def patterns():
    P = pd.read_csv(os.path.join(R, "patterns/out/A_ha_vzory.csv"))
    P = P[P.vyber.str.startswith("nej")]
    fig, ax = plt.subplots(figsize=(7, 5.5))
    for lab, col in (("nejlepsi 10 (2011-18)", GREEN), ("nejhorsi 10 (2011-18)", RED)):
        q = P[P.vyber == lab]
        ax.scatter(q.excess_2011_18, q.excess_2019_26, color=col, s=14, label=lab.replace("nejlepsi", "nejlepší").replace("nejhorsi", "nejhorší"))
    lim = max(P.excess_2011_18.abs().max(), P.excess_2019_26.abs().max())
    ax.plot([-lim, lim], [-lim, lim], color=MUTED, ls="--", lw=1); ax.axhline(0, color=INK, lw=0.8); ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlabel("excess 2011–18 (ATR)"); ax.set_ylabel("excess 2019–26 (ATR)")
    ax.set_title("HA formace: výběr 2011–18 v testu 2019–26 nedrží"); ax.legend(frameon=False)
    save(fig, "formace.png")


if __name__ == "__main__":
    for f in (hours, weekdays, drawdowns, mm, delta_vwap, patterns):
        f(); print(f.__name__, flush=True)
