"""Charts for the grid trigger research (matplotlib). Env DPI and CHART_OUT override resolution and folder."""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
from alpha import bh_points, daily

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUTD = os.environ.get("CHART_OUT", os.path.join(SRC, "charts"))
DPI = int(os.environ.get("DPI", 130))
INK = "#1f2328"; MUTED = "#6e7781"; GRID = "#d8dee4"
C = {"fade": "#c2410c", "mom": "#1d4ed8", "null": "#6e7781", "long": "#15803d", "bh": "#111827"}
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold"})
RULE_ORDER = ["fade oboji", "momentum oboji", "nahoda (null)", "fade long (pokles->long)",
              "momentum long (rust->long)", "long vzdy (prikupovani+prumerovani)", "fade short (rust->short)",
              "momentum short (pokles->short)"]
RULE_CZ = {"fade oboji": "fade obě strany", "momentum oboji": "momentum obě strany", "nahoda (null)": "náhodný směr",
           "fade long (pokles->long)": "fade long (pokles→long)", "momentum long (rust->long)": "momentum long (růst→long)",
           "long vzdy (prikupovani+prumerovani)": "long vždy (přikup.+průměr.)",
           "fade short (rust->short)": "fade short (růst→short)", "momentum short (pokles->short)": "momentum short (pokles→short)"}


def save(fig, name):
    os.makedirs(OUTD, exist_ok=True)
    fig.savefig(os.path.join(OUTD, name), dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def renko():
    A = pd.read_csv(os.path.join(SRC, "A_renko.csv"))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    for m, col, lab in ((1, C["mom"], "1min bary (použito)"), (5, C["fade"], "5min bary (hrubší cesta)")):
        a = A[A.bary_min == m]
        ax[0].plot(a.X_body, a.p_pokracovani, "o-", color=col, label=lab)
    ax[0].axhline(0.5, color=INK, lw=1, ls="--"); ax[0].set_xscale("log")
    ax[0].set_xticks([1, 2, 3, 4, 6, 10, 20, 50]); ax[0].set_xticklabels([1, 2, 3, 4, 6, 10, 20, 50])
    ax[0].set_xlabel("pohyb X (body)"); ax[0].set_ylabel("P(další pohyb X stejným směrem)")
    ax[0].set_title("Pokračování pohybu: 0,5 = náhodná procházka"); ax[0].legend(frameon=False)
    a = A[A.bary_min == 1].set_index("X_body")
    yrs = [str(y) for y in range(2011, 2027)]
    for x, col in ((2, "#94a3b8"), (6, C["fade"]), (10, C["mom"]), (20, C["long"])):
        ax[1].plot(range(2011, 2027), a.loc[x, yrs].to_numpy(), "o-", ms=3, color=col, label=f"X = {x} b.")
    ax[1].axhline(0.5, color=INK, lw=1, ls="--"); ax[1].set_title("Podle roku (1min)"); ax[1].legend(frameon=False, ncol=2)
    ax[1].set_ylabel("P(pokračování)")
    save(fig, "renko_pokracovani.png")


def rules_bar():
    files = [("body", "B_grid_body.csv"), ("denní ATR", "C_grid_atr_d.csv"), ("hodinové ATR", "C_grid_atr_h.csv"),
             ("týdenní ATR", "C_grid_atr_w.csv")]
    fig, ax = plt.subplots(figsize=(12, 4.8))
    w = 0.2
    for k, (lab, f) in enumerate(files):
        R = pd.read_csv(os.path.join(SRC, f))
        m = R.groupby("pravidlo").hrube_b_obchod.mean().reindex(RULE_ORDER)
        ax.bar(np.arange(len(m)) + (k - 1.5) * w, m.to_numpy(), w, label=lab,
               color=["#1d4ed8", "#60a5fa", "#f59e0b", "#15803d"][k])
    ax.axhline(0, color=INK, lw=1)
    ax.axhline(0.5, color=C["fade"], lw=1.2, ls="--"); ax.text(7.45, 0.52, "náklad 0,5 b./obchod", color=C["fade"], ha="right")
    ax.set_xticks(range(len(RULE_ORDER))); ax.set_xticklabels([RULE_CZ[r] for r in RULE_ORDER], rotation=20, ha="right")
    ax.set_ylabel("hrubý zisk (body / obchod)")
    ax.set_title("Průměr všech systémů podle pravidla – hrubě, před náklady")
    ax.legend(frameon=False, ncol=4)
    save(fig, "pravidla_hrube.png")


def heat():
    R = pd.read_csv(os.path.join(SRC, "B_grid_body.csv"))
    R = R[R.max_obchodu.astype(str) == "neomezeno"]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    for ax, rule in zip(axs, ("fade oboji", "momentum oboji", "fade long (pokles->long)")):
        p = R[R.pravidlo == rule].pivot_table(index="SL_body", columns="X_body", values="cisty_b_obchod_0.5", aggfunc="mean")
        im = ax.imshow(p.to_numpy(), cmap="RdBu", vmin=-1.5, vmax=1.5, aspect="auto", origin="lower")
        ax.set_xticks(range(p.shape[1])); ax.set_xticklabels(p.columns)
        ax.set_yticks(range(p.shape[0])); ax.set_yticklabels(p.index)
        for i in range(p.shape[0]):
            for j in range(p.shape[1]):
                ax.text(j, i, f"{p.iloc[i, j]:.2f}", ha="center", va="center", fontsize=7, color=INK)
        ax.set_xlabel("trigger X (body)"); ax.set_ylabel("SL (body)"); ax.set_title(RULE_CZ[rule]); ax.grid(False)
    fig.colorbar(im, ax=axs, shrink=0.8, label="čistý zisk b./obchod (průměr přes RRR)")
    fig.suptitle("Čistý výsledek gridu po nákladu 0,5 b. – modrá = zisk, červená = ztráta", fontweight="bold")
    save(fig, "heat_cisty_body.png")


def nmax():
    R = pd.read_csv(os.path.join(SRC, "B_grid_body.csv"))
    p = R.pivot_table(index="max_obchodu", columns="pravidlo", values="body_rocne_0.5", aggfunc="median")
    p = p.reindex(["1", "3", "10", "neomezeno"])
    fig, ax = plt.subplots(figsize=(11, 4.2))
    for r, col in (("fade oboji", C["fade"]), ("momentum oboji", C["mom"]), ("nahoda (null)", C["null"]),
                   ("fade long (pokles->long)", "#f59e0b"), ("long vzdy (prikupovani+prumerovani)", C["long"])):
        ax.plot(range(4), p[r].to_numpy(), "o-", color=col, label=RULE_CZ[r])
    ax.set_xticks(range(4)); ax.set_xticklabels(["max 1", "max 3", "max 10", "neomezeno"])
    ax.axhline(0, color=INK, lw=1); ax.set_ylabel("čisté body za rok (medián systémů)")
    ax.set_title("Víc současně otevřených obchodů = víc obchodů = víc nákladů"); ax.legend(frameon=False, ncol=2)
    save(fig, "max_obchodu.png")


def equity():
    z = E.load()
    cfgs = [dict(X_body=10, SL_body=10, RRR=1.2, pravidlo=r, max_obchodu=1)
            for r in ("fade long (pokles->long)", "fade oboji", "momentum oboji", "nahoda (null)")]
    cfgs.append(dict(X_body=30, SL_body=15, RRR=5.0, pravidlo="momentum long (rust->long)", max_obchodu=3))
    net, days = daily(z, cfgs)
    bh = np.nan_to_num(bh_points(z, days))
    fig, ax = plt.subplots(figsize=(12, 5))
    cols = ["#f59e0b", C["fade"], C["mom"], C["null"], C["long"]]
    labs = ["fade long X10 TP12/SL10 (tvůj příklad)", "fade obě strany X10 TP12/SL10", "momentum obě strany X10 TP12/SL10",
            "náhodný směr X10 TP12/SL10", "nejlepší: momentum long X30 SL15 RRR5"]
    dt = pd.DatetimeIndex(days)
    for y, col, lab in zip(net, cols, labs):
        ax.plot(dt, np.cumsum(y), color=col, lw=1.3, label=lab)
    ax.plot(dt, np.cumsum(bh), color=C["bh"], lw=1.6, label="Buy & hold 1 kontrakt ES")
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_ylabel("kumulativně body (1 kontrakt, po nákladu 0,5 b.)")
    ax.set_title("Equity grid systémů 2011–2026 proti buy & hold"); ax.legend(frameon=False, fontsize=8, loc="lower left")
    save(fig, "equity.png")


def vwap():
    p = os.path.join(SRC, "D_vwap_filtr.csv")
    if not os.path.exists(p):
        return
    D = pd.read_csv(p)
    pv = D.pivot_table(index="filtr", columns="pravidlo", values="hrube_b_obchod", aggfunc="mean")
    order = ["bez filtru", "ve smeru W-VWAP", "proti W-VWAP", "ve smeru M-VWAP", "proti M-VWAP", "ve smeru W+M"]
    pv = pv.reindex(order)
    fig, ax = plt.subplots(figsize=(12, 4.6))
    w = 0.2
    for k, (r, col) in enumerate((("fade long (pokles->long)", "#f59e0b"), ("momentum long (rust->long)", C["long"]),
                                  ("fade short (rust->short)", C["fade"]), ("momentum short (pokles->short)", C["mom"]))):
        ax.bar(np.arange(len(order)) + (k - 1.5) * w, pv[r].to_numpy(), w, color=col, label=RULE_CZ[r])
    ax.axhline(0, color=INK, lw=1); ax.axhline(0.5, color=C["fade"], ls="--", lw=1.2)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(["bez filtru", "ve směru týdenního VWAP", "proti týdennímu", "ve směru měsíčního",
                        "proti měsíčnímu", "ve směru týd.+měs."], rotation=15)
    ax.set_ylabel("hrubý zisk b./obchod"); ax.legend(frameon=False, ncol=2)
    ax.set_title("VWAP filtr (long jen nad VWAP, short jen pod) – čárkovaně náklad 0,5 b.")
    save(fig, "vwap_filtr.png")


def path():
    F = pd.read_csv(os.path.join(SRC, "F_cesta_kalibrace.csv"))
    cols = ["5min normal", "5min blizsi extrem", "5min obracene", "1min normal", "1min blizsi extrem", "1min obracene"]
    m = F.groupby("pravidlo")[cols].mean()
    fig, ax = plt.subplots(figsize=(11, 4.4))
    w = 0.38
    labs = ["5min: směr baru", "5min: bližší extrém", "5min: obrácené", "1min: směr baru (použito)",
            "1min: bližší extrém", "1min: obrácené"]
    for k, (r, col) in enumerate((("fade oboji", C["fade"]), ("momentum oboji", C["mom"]))):
        ax.bar(np.arange(len(cols)) + (k - 0.5) * w, m.loc[r, cols].to_numpy(), w, color=col, label=RULE_CZ[r])
    ax.axhline(0, color=INK, lw=1)
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(labs, rotation=15)
    ax.set_ylabel("hrubý zisk b./obchod")
    ax.set_title("Pořadí high/low uvnitř baru: čím jemnější data, tím blíž nule (1min je pravda pro 5min test)")
    ax.legend(frameon=False)
    save(fig, "cesta_v_baru.png")


if __name__ == "__main__":
    for f in (renko, rules_bar, heat, nmax, equity, vwap, path):
        f(); print(f.__name__, flush=True)
