"""Charts for the anchors / impulse research."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
CH = os.path.join(OUT, "charts"); os.makedirs(CH, exist_ok=True)
INK = "#1f2328"; MUTED = "#6e7781"; GRID = "#d8dee4"; BLUE = "#1d4ed8"; RED = "#c2410c"; GREEN = "#15803d"; AMBER = "#f59e0b"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titleweight": "bold"})
BK = ["0.1-0.25", "0.25-0.5", "0.5-1.0", "1.0-2.0", "2.0-4.0"]


def save(fig, n):
    fig.savefig(os.path.join(CH, n), dpi=130, bbox_inches="tight", facecolor="white"); plt.close(fig)


def hit():
    H = pd.read_csv(os.path.join(OUT, "A_dosazeni_kotev.csv"))
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2), sharey=True)
    for ax, h in zip(axs, ("2h", "1d", "5d")):
        g = H[H.horizont == h].groupby("vzdalenost_atr")[["p_dosazeni", "p_dosazeni_zrcadlo"]].mean().reindex(BK)
        x = np.arange(len(BK))
        ax.bar(x - 0.2, g.p_dosazeni * 100, 0.4, color=BLUE, label="kotva (cíl)")
        ax.bar(x + 0.2, g.p_dosazeni_zrcadlo * 100, 0.4, color=MUTED, label="zrcadlová úroveň na druhé straně")
        ax.set_xticks(x); ax.set_xticklabels(BK); ax.set_title(f"Dosažení do {h}"); ax.set_xlabel("vzdálenost kotvy (ATR)")
    axs[0].set_ylabel("pravděpodobnost dosažení (%)"); axs[0].legend(frameon=False)
    fig.suptitle("Kotvy (VWAP D/W/M, POC, VAH, VAL, extrémy dne) se dosahují stejně často jako zrcadlová úroveň", fontweight="bold")
    save(fig, "dosazeni_kotev.png")


def mae():
    H = pd.read_csv(os.path.join(OUT, "A_dosazeni_kotev.csv"))
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for h, c in (("1d", BLUE), ("5d", AMBER)):
        g = H[H.horizont == h].groupby("vzdalenost_atr")[["MAE_median_atr", "MAE_p90_atr"]].mean().reindex(BK)
        ax.plot(BK, g.MAE_median_atr, "o-", color=c, label=f"medián ({h})")
        ax.plot(BK, g.MAE_p90_atr, "s--", color=c, label=f"90. percentil ({h})")
    ax.set_xlabel("vzdálenost kotvy (ATR)"); ax.set_ylabel("nepříznivý pohyb před dosažením (ATR)")
    ax.set_title("Jak hluboko cena nejdřív jde proti pozici, než kotvu dosáhne"); ax.legend(frameon=False)
    save(fig, "mae_pred_cilem.png")


def tdist():
    T = pd.read_csv(os.path.join(OUT, "E_efekt_kotev_vyvazeny.csv"))
    x = T[T.mereni == "P(dosazeni)"].t.dropna(); y = T[T.mereni == "EV cisty b."].t.dropna()
    fig, axs = plt.subplots(1, 2, figsize=(13, 4))
    for ax, v, ttl in ((axs[0], x, "Pravděpodobnost dosažení (490 testů)"), (axs[1], y, "Čistá očekávaná hodnota (1960 testů)")):
        ax.hist(v.clip(-6, 6), bins=40, color=BLUE, density=True)
        g = np.linspace(-6, 6, 200); ax.plot(g, np.exp(-g * g / 2) / np.sqrt(2 * np.pi), color=RED, lw=2, label="náhoda N(0,1)")
        ax.axvline(-2, color=MUTED, ls="--"); ax.axvline(2, color=MUTED, ls="--")
        ax.set_title(f"{ttl}: |t| > 2 v {100 * (v.abs() > 2).mean():.1f} % (náhoda 5 %)"); ax.set_xlabel("t-statistika efektu kotvy"); ax.legend(frameon=False)
    save(fig, "t_rozdeleni.png")


def horizons():
    F = pd.read_csv(os.path.join(OUT, "F_souhrn_kotvy.csv"))
    F = F[(F.skupina == "vse") & (F.mereni == "EV") & (F.stop_atr.astype(str).isin(["1.0", "bez stopu"]))]
    order = ["2h", "3h", "12h", "dnes RTH close", "1d", "2d", "5d"]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for s, c in (("1.0", RED), ("bez stopu", GREEN)):
        g = F[F.stop_atr.astype(str) == s].set_index("horizont").reindex(order)
        ax.plot(order, g.T_prumer, "o-", color=c, label=f"cíl = kotva, stop {s if s != 'bez stopu' else 'žádný'}" + (" ATR" if s != "bez stopu" else ""))
        ax.plot(order, g.zrcadlo_prumer, "x--", color=c, alpha=0.6, label="zrcadlová úroveň")
    ax.axhline(0, color=INK, lw=0.8); ax.set_ylabel("čistý výsledek (body na obchod, po 0,5 b.)")
    ax.set_title("Držení přes noc / dny: ztráta se zmenšuje jen proto, že trh roste"); ax.legend(frameon=False, fontsize=8)
    save(fig, "horizonty_ev.png")


def impulse():
    G = pd.read_csv(os.path.join(OUT, "G_impuls_pauza.csv"))
    g = G[(G.podminka == "vse") & (G.mereni == "reverzni zavod 1d (origin driv)") & (G.udalosti >= 100)].copy()
    g["p"] = (g.efekt + 0.5) * 100; g["se"] = g.se * 100
    g["lab"] = [f"imp {a} ATR\npauza {b} min\nrozsah {c}" for a, b, c in zip(g.impuls_ATR, g.pauza_min, g.rozsah_pauzy_ATR)]
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.bar(range(len(g)), g.p, yerr=1.96 * g.se, color=BLUE, capsize=3); ax.axhline(50, color=RED, lw=1.5, ls="--")
    ax.set_xticks(range(len(g))); ax.set_xticklabels(g.lab, fontsize=7); ax.set_ylim(35, 65)
    ax.set_ylabel("návrat k počátku impulsu dřív než pokračování (%)")
    ax.set_title("Impuls → pauza: návrat vs pokračování = 50 % (náhodná procházka)")
    save(fig, "impuls_pauza.png")


if __name__ == "__main__":
    for f in (hit, mae, tdist, horizons, impulse):
        f(); print(f.__name__, flush=True)
