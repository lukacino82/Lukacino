"""Block 6a - recurring formations on volume bars: Heikin-Ashi colour sequences x position vs the daily VWAP x sign
of the cumulative delta. Volume bars are built from whole 1-minute bars (a bar closes when it reaches the volume),
like the 100k / 180k charts; 25k bars as the intraday case. Every pattern = last 4 HA colours (16) x strong last
candle (no opposite wick) x above/below daily VWAP x CD > 0 / < 0 = 128 patterns. Outcome: change over the next
1 / 3 / 6 bars in ATR minus the mean of all bars. Patterns ranked on 2011-18, the top and bottom 10 checked on 2019-26.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/Lukacino/research/delta_vwap")
import prep as P

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def volume_bars(f, size):
    cv = f.V.cumsum().to_numpy()
    k = (cv // size).astype(np.int64)
    g = f.groupby(k)
    b = g.agg(ts=("ts", "last"), O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"),
              V=("V", "sum"), cd=("cd_g", "last"), vw=("vwap_d", "last"), atr=("atr", "last"), gday=("gday", "last"))
    return b.reset_index(drop=True)


def heikin(b):
    hc = (b.O + b.H + b.L + b.C).to_numpy() / 4
    ho = np.empty(len(b)); ho[0] = (b.O.iloc[0] + b.C.iloc[0]) / 2
    for i in range(1, len(b)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    hh = np.maximum(b.H.to_numpy(), np.maximum(ho, hc)); hl = np.minimum(b.L.to_numpy(), np.minimum(ho, hc))
    up = hc > ho
    strong = np.where(up, np.isclose(np.minimum(ho, hc), hl), np.isclose(np.maximum(ho, hc), hh))
    return up, strong


def run(f, size):
    b = volume_bars(f, size)
    up, strong = heikin(b)
    code = np.zeros(len(b), np.int64)
    for k in range(4):
        code = code * 2 + np.r_[np.zeros(k, bool), up[:len(b) - k]].astype(np.int64)
    pat = code * 8 + strong * 4 + (b.C.to_numpy() > b.vw.to_numpy()) * 2 + (b.cd.to_numpy() > 0)
    C = b.C.to_numpy(); atr = b.atr.to_numpy()
    rows = []
    disc = b.ts.to_numpy() < np.datetime64("2019-01-01")
    res = {}
    for h in (1, 3, 6):
        fw = (np.r_[C[h:], np.full(h, np.nan)] - C) / atr
        x = fw - np.nanmean(fw)
        res[h] = x
    df = pd.DataFrame({"pat": pat, "disc": disc, **{f"x{h}": res[h] for h in res}}).iloc[4:]
    for h in (1, 3, 6):
        g1 = df[df.disc].groupby("pat")[f"x{h}"].agg(["mean", "std", "size"])
        g2 = df[~df.disc].groupby("pat")[f"x{h}"].agg(["mean", "std", "size"])
        g1["t"] = g1["mean"] / g1["std"] * np.sqrt(g1["size"] / h)
        g2["t"] = g2["mean"] / g2["std"] * np.sqrt(g2["size"] / h)
        top = g1[g1["size"] >= 100].sort_values("t")
        for lab, sel in (("nejlepsi 10 (2011-18)", top.tail(10).index), ("nejhorsi 10 (2011-18)", top.head(10).index)):
            for p in sel:
                rows.append(dict(bary=f"{size // 1000}k", horizont_baru=h, vyber=lab, vzor=describe(p),
                                 n_2011_18=int(g1.loc[p, "size"]), excess_2011_18=g1.loc[p, "mean"], t_2011_18=g1.loc[p, "t"],
                                 n_2019_26=int(g2.loc[p, "size"]) if p in g2.index else 0,
                                 excess_2019_26=g2.loc[p, "mean"] if p in g2.index else np.nan,
                                 t_2019_26=g2.loc[p, "t"] if p in g2.index else np.nan))
        # correlation of pattern means between the two periods (stability of the whole ranking)
        j = g1.join(g2, lsuffix="_1", rsuffix="_2", how="inner")
        j = j[(j.size_1 >= 100) & (j.size_2 >= 100)]
        rows.append(dict(bary=f"{size // 1000}k", horizont_baru=h, vyber="korelace poradi 2011-18 vs 2019-26",
                         vzor=f"{len(j)} vzoru", excess_2011_18=j.mean_1.corr(j.mean_2, method="spearman")))
    return rows, len(b)


def describe(p):
    cd = p % 2; vw = (p // 2) % 2; st = (p // 4) % 2; code = p // 8
    cols = "".join("Z" if (code >> k) & 1 else "C" for k in range(4))      # oldest -> newest, Z green, C red
    return f"HA {cols} {'silna' if st else 'normalni'} {'nad' if vw else 'pod'} VWAP CD{'+' if cd else '-'}"


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    f = P.load()
    allrows = []
    for size in (25000, 100000, 180000):
        rows, nb = run(f, size); allrows += rows
        print(size, nb, "baru", flush=True)
    R = pd.DataFrame(allrows)
    R.round(4).to_csv(os.path.join(OUT, "A_ha_vzory.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(R.round(3).to_string())
