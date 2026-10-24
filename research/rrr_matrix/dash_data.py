"""Datasets for the RRR matrix dashboard (written to /tmp/claude-0/dash)."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import analysis as A
import engine as E

OUT = "/tmp/claude-0/dash"


def equity(bars, mode, h, side, sl, rrr, risk=0.01):
    z = A.load(mode, h, side)
    i_sl = int(np.argmin(np.abs(z["slv"] - sl)))
    R, ex, win, loss, opn = A.outcomes(z, i_sl, rrr)
    order = np.argsort(z["ent"], kind="stable")
    tk = A.sequence(z["ent"][order], ex[order], np.ones(len(order), bool))
    idx = order[tk]
    exit_bar = np.minimum(z["ent"][idx] + ex[idx], len(bars) - 1)
    eday = bars.gday.iloc[exit_bar].to_numpy()
    return pd.Series(risk * R[idx], index=eday).groupby(level=0).sum()


def main():
    os.makedirs(OUT, exist_ok=True)
    bars = E.load_bars()[["ts", "gday", "Close"]]
    a = pd.read_csv("out/A_grand.csv")
    a = a[["mode", "horizont", "smer", "SL", "RRR", "win", "nahodna_win", "open", "R", "R_2011_18", "R_2019_26"]].round(4)
    a.to_csv(f"{OUT}/grid.csv", index=False)
    # equity curves (risk 1 % per trade, one position at a time), weekly samples
    dc = bars.groupby("gday").Close.last()
    days = dc.loc["2011-01-01":].index
    curves = {
        "Buy & hold ES": None,
        "ATR 20D long · SL 0,25 ATR týdne · 1:20": ("atr", "20D", "long", 0.25, 20),
        "ATR 5D long · SL 2 ATR dne · 1:1,5": ("atr", "5D", "long", 2.0, 1.5),
        "Body 5D long · SL 20 b. · 1:3": ("points", "5D", "long", 20, 3),
        "Body intraday long · SL 20 b. · 1:1,5": ("points", "intraday", "long", 20, 1.5),
        "Body intraday long · SL 10 b. · 1:10": ("points", "intraday", "long", 10, 10),
    }
    rows = []
    for name, spec in curves.items():
        if spec is None:
            cash = pd.read_parquet(f"{OUT}/cash_daily.parquet").C            # true index level (alpha_fix.py)
            cash = cash.loc[days[0]:]
            eq = cash / cash.iloc[0]
        else:
            r = equity(bars, *spec).reindex(days).fillna(0)
            eq = (1 + r).cumprod()
        w = eq.resample("W-FRI").last().dropna()
        for d, v in w.items():
            rows.append(dict(strategie=name, tyden=d.strftime("%Y-%m-%d"), equity=round(float(v), 4)))
    pd.DataFrame(rows).to_csv(f"{OUT}/equity.csv", index=False)
    # R by entry hour for a few combinations
    hrows = []
    for mode, h, side, sl, r in (("points", "intraday", "long", 20, 1.5), ("points", "intraday", "short", 20, 1.5),
                                 ("points", "5D", "long", 20, 3), ("points", "intraday", "long", 10, 10)):
        z = A.load(mode, h, side)
        i_sl = int(np.argmin(np.abs(z["slv"] - sl)))
        R, *_ = A.outcomes(z, i_sl, r)
        M = A.meta(bars, z["ent"])
        per = np.where(M.ts < A.SPLIT, "2011–18", "2019–26")
        g = pd.DataFrame({"hour": M.hour, "per": per, "R": R}).groupby(["hour", "per"]).R.mean().unstack()
        for hr, rr in g.iterrows():
            hrows.append(dict(kombinace=f"{h} {side} · SL {sl} b. · 1:{str(r).replace('.', ',')}", hodina=int(hr),
                              R_2011_18=round(rr["2011–18"], 4), R_2019_26=round(rr["2019–26"], 4)))
    pd.DataFrame(hrows).to_csv(f"{OUT}/hours.csv", index=False)
    c = pd.read_csv("out/C_streaks.csv")
    c = c[(c.smer == "long")][["horizont", "SL", "RRR", "obchodu_rocne", "win", "max_serie", "iid_max_serie",
                               "serie>=10", "serie>=20", "serie>=50"]].round(3)
    c.columns = ["horizont", "SL", "RRR", "obchodu_rocne", "win", "max_serie", "iid_max_serie", "serie10", "serie20", "serie50"]
    c.to_csv(f"{OUT}/streaks.csv", index=False)
    pd.read_csv("out/D_min_winners.csv").round(4).to_csv(f"{OUT}/minwin.csv", index=False)
    f = pd.read_csv("out/F_stophunt.csv")
    f = f[~f.varianta.str.contains("extrém")]
    g = f.groupby(["level", "smer", "varianta"]).agg(n=("n", "max"), R=("R", "mean"), R_nahodny=("R_nahodny_vstup", "mean")).reset_index()
    g["rozdil"] = g.R - g.R_nahodny
    g.round(4).to_csv(f"{OUT}/stophunt.csv", index=False)
    e = pd.read_csv("out/E_alpha.csv")[["mode", "horizont", "smer", "SL", "RRR", "obchodu_2019_26", "R_2019_26", "CAGR", "maxDD", "alfa_rok", "alfa_t", "BH_CAGR"]].round(4)
    e.to_csv(f"{OUT}/alpha.csv", index=False)
    for fn in os.listdir(OUT):
        print(fn, os.path.getsize(os.path.join(OUT, fn)))


if __name__ == "__main__":
    main()
