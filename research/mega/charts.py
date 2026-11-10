"""Charts for the mega scan."""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
CH = os.path.join(OUT, "charts"); os.makedirs(CH, exist_ok=True)
C = "/tmp/claude-0/data/mega/"
INK = "#1f2328"; MUTED = "#6e7781"; GRID = "#d8dee4"; BLUE = "#1d4ed8"; RED = "#c2410c"; GREEN = "#15803d"; AMBER = "#f59e0b"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titleweight": "bold"})


def save(fig, n):
    fig.savefig(os.path.join(CH, n), dpi=130, bbox_inches="tight", facecolor="white"); plt.close(fig)


def typ_d(o):
    return np.where(o.str.startswith("long"), "long TP/SL", np.where(o.str.startswith("short"), "short TP/SL",
                    np.where(o.isin(["noc (close->open)", "dalsi RTH (open->close)", "drzeni 1d"]), "horizont do 1 dne", "drzeni 2-20 dni")))


def counts():
    rows = []
    def add(layer, R, kind, typf):
        s = np.sign(R.tD); v = R.tV * s; h = R.tH * s; ty = typf(R.outcome)
        for t_ in np.unique(ty):
            m = ty == t_
            rows.append(dict(vrstva=layer, typ=t_, beh=kind, kandidatu=int(m.sum()), potvrzeno_V2_H2=int(((v >= 2) & (h >= 2))[m].sum()),
                             potvrzeno_V3_H3=int(((v >= 3) & (h >= 3))[m].sum())))
    add("denni", pd.read_parquet(C + "daily_candidates.parquet"), "skutecna data", typ_d)
    for k in (1, 2, 3):
        add("denni", pd.read_parquet(C + f"daily_candidates_null{k}.parquet"), f"nahoda {k}", typ_d)
    th = lambda o: np.where(o.str.startswith("long"), "long TP/SL", np.where(o.str.startswith("short"), "short TP/SL", "horizont"))
    add("hodinova", pd.read_parquet(C + "hourly_candidates_real.parquet"), "skutecna data", th)
    for k in (1, 2):
        add("hodinova", pd.read_parquet(C + f"hourly_candidates_null{k}.parquet"), f"nahoda {k}", th)
    T = pd.DataFrame(rows)
    T["nahoda"] = T.beh.str.startswith("nahoda")
    S = T.groupby(["vrstva", "typ", "nahoda"])[["kandidatu", "potvrzeno_V2_H2", "potvrzeno_V3_H3"]].mean().unstack()
    S.columns = [f"{a}_{'nahoda' if b else 'data'}" for a, b in S.columns]
    S = S.reset_index()
    S["pomer_kandidatu"] = S.kandidatu_data / S.kandidatu_nahoda
    S["pomer_potvrzenych"] = S.potvrzeno_V2_H2_data / S.potvrzeno_V2_H2_nahoda.replace(0, np.nan)
    S.round(2).to_csv(os.path.join(OUT, "sken_data_vs_nahoda.csv"), index=False)
    fig, ax = plt.subplots(figsize=(12, 4.4))
    lab = [f"{a}\n{b}" for a, b in zip(S.vrstva, S.typ)]; x = np.arange(len(S))
    ax.bar(x - 0.2, S.potvrzeno_V2_H2_data.clip(lower=0.5), 0.4, color=BLUE, label="skutečná data")
    ax.bar(x + 0.2, S.potvrzeno_V2_H2_nahoda.clip(lower=0.5), 0.4, color=MUTED, label="náhodná kontrola (průměr běhů)")
    ax.set_yscale("log"); ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=8)
    ax.set_ylabel("počet objevů potvrzených ve 2 dalších obdobích (log)")
    ax.set_title("Kolik objevů přežije: skutečná data vs náhoda"); ax.legend(frameon=False)
    save(fig, "objevy_vs_nahoda.png")
    return S


def score():
    S = pd.read_csv(os.path.join(OUT, "score_dalsi_den.csv"))
    fig, ax = plt.subplots(figsize=(11, 4.4))
    per = list(S.obdobi.unique()); grp = [g for g in S.skupina.unique()]
    w = 0.26
    for k, p in enumerate(per):
        s = S[S.obdobi == p].set_index("skupina").reindex(grp)
        ax.bar(np.arange(len(grp)) + (k - 1) * w, s.dalsi_den_pct, w, label=p, color=[BLUE, AMBER, GREEN][k])
    ax.axhline(0, color=INK, lw=0.8); ax.set_xticks(range(len(grp)))
    ax.set_xticklabels(["bez slabosti", "slabost", "silná slabost", "síla (překoupeno)", "všechny dny"])
    ax.set_ylabel("průměrný výnos dalšího dne (%)"); ax.set_title("Skóre slabosti → výnos dalšího dne (skóre sestavené jen z dat do 2020)")
    ax.legend(frameon=False)
    save(fig, "skore_dalsi_den.png")


def equity():
    E = pd.read_parquet(os.path.join(OUT, "score_equity.parquet"))
    fig, ax = plt.subplots(figsize=(12, 5))
    show = {"Buy & hold 1x": INK, "S1: slabost -> 2x (noc i den)": BLUE, "S2: slabost 2x, silna slabost 3x": GREEN,
            "S6: jen slabost, silna 2x": AMBER, "S5: jen slabost (jinak mimo trh)": RED}
    for k, c in show.items():
        ax.plot(E.index, E[k], color=c, lw=1.4, label=k)
    ax.axvline(pd.Timestamp("2021-01-01"), color=MUTED, ls="--"); ax.text(pd.Timestamp("2021-02-01"), 1.1, "holdout 2021–26", color=MUTED)
    ax.set_yscale("log"); ax.set_title("Equity (log, start = 1): strategie ze skóre slabosti vs buy & hold"); ax.legend(frameon=False, fontsize=8)
    save(fig, "equity_skore.png")
    dd = E / E.cummax() - 1
    fig, ax = plt.subplots(figsize=(12, 3.6))
    for k, c in show.items():
        ax.plot(dd.index, dd[k] * 100, color=c, lw=1, label=k)
    ax.set_title("Propad od maxima (%)"); ax.legend(frameon=False, fontsize=7, ncol=3)
    save(fig, "propady_skore.png")


def thist():
    fig, ax = plt.subplots(figsize=(10, 4.2))
    r = pd.read_csv(os.path.join(OUT, "daily_scan_thist_real.csv")); n = pd.read_csv(os.path.join(OUT, "daily_scan_thist_null1.csv"))
    ax.step(r.t_lo, r["count"], color=BLUE, label="skutečná data"); ax.step(n.t_lo, n["count"], color=RED, label="náhodná kontrola")
    g = np.linspace(-10, 10, 400); ax.plot(g, r["count"].sum() * 0.25 * np.exp(-g * g / 2) / np.sqrt(2 * np.pi), color=MUTED, ls="--", label="teoretická N(0,1)")
    ax.set_yscale("log"); ax.set_ylim(1, None); ax.set_xlabel("t-statistika v období 2008–2015"); ax.set_ylabel("počet testů (log)")
    ax.set_title("147 mil. denních testů: rozdělení t je stejné jako u náhodné kontroly"); ax.legend(frameon=False)
    save(fig, "t_rozdeleni.png")


if __name__ == "__main__":
    S = counts(); pd.set_option("display.width", 250); print(S.round(2).to_string())
    score(); equity(); thist(); print("ok")
