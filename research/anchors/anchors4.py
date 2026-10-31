"""Anchors pooled over all anchors / distance buckets 0.25-2 ATR (H5: overnight vs same-day close; effect vs mirror).
Drift-balanced effect (anchor above + below), cluster-robust SE with 2-week blocks."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors2 as A2
from anchors import OUT, anchors as get_anchors
sys.path.insert(0, "/home/user/Lukacino/research/delta_vwap")
import prep as P


def pooled(x, d, blk, grp):
    df = pd.DataFrame({"g": grp, "dir": d, "blk": blk, "x": x.astype(np.float64)})
    g = df.groupby(["g", "dir"]).x
    df["mu"] = g.transform("mean"); df["w"] = 0.5 / g.transform("size")
    eff = (df.w * df.x).groupby(df.g).sum()
    e = (df.w * (df.x - df.mu)).groupby([df.g, df.blk]).sum()
    se = np.sqrt((e ** 2).groupby(level=0).sum())
    return eff, se


def main():
    f = P.load(); A = get_anchors(f); rng = np.random.default_rng(11)
    R = A2.make_events(f, A, False, rng); R["wk"] = A2.week_of(f, R)
    hit_r, net_r, _, _ = A2.outcomes(f, R); hit_m, net_m, _, _ = A2.outcomes(f, R, mirror=True)
    keep = (R.d_atr.to_numpy() >= 0.25) & (R.d_atr.to_numpy() < 2.0)
    d = R["dir"].to_numpy()[keep]; blk = (R.wk.to_numpy() // 2)[keep]
    ts = f.ts.to_numpy()[R.i.to_numpy()][keep]; disc = ts < np.datetime64("2019-01-01")
    grpname = np.where(R.anchor.str.startswith("VWAP"), "VWAP D/W/M", np.where(R.anchor.str.contains("High|Low"), "High/Low dne", "profil POC/VAH/VAL"))[keep]
    rows = []
    for h in A2.HNAMES:
        for kind, s in [("P(dosazeni)", None)] + [("EV", s) for s in A2.SNAMES]:
            xr = hit_r[h][keep] if kind == "P(dosazeni)" else net_r[(h, s)][keep]
            xm = hit_m[h][keep] if kind == "P(dosazeni)" else net_m[(h, s)][keep]
            for gname, gm in (("vse", np.ones(keep.sum(), bool)), ("VWAP D/W/M", grpname == "VWAP D/W/M"),
                              ("profil POC/VAH/VAL", grpname == "profil POC/VAH/VAL"), ("High/Low dne", grpname == "High/Low dne")):
                eff, se = pooled((xr - xm)[gm], d[gm], blk[gm], np.zeros(gm.sum()))
                e1, s1 = pooled((xr - xm)[gm & disc], d[gm & disc], blk[gm & disc], np.zeros((gm & disc).sum()))
                e2, s2 = pooled((xr - xm)[gm & ~disc], d[gm & ~disc], blk[gm & ~disc], np.zeros((gm & ~disc).sum()))
                sd = float(np.std(xr[gm])) if kind == "EV" else np.nan
                rows.append(dict(skupina=gname, horizont=h, mereni=kind, stop_atr="-" if kind == "P(dosazeni)" else (s if s else "bez stopu"),
                                 udalosti=int(gm.sum()), T_prumer=float(xr[gm].mean()), zrcadlo_prumer=float(xm[gm].mean()),
                                 EV_na_sd=float(xr[gm].mean() / sd) if sd else np.nan,
                                 efekt_vyvazeny=float(eff.iloc[0]), t=float(eff.iloc[0] / se.iloc[0]),
                                 efekt_2011_18=float(e1.iloc[0]), efekt_2019_26=float(e2.iloc[0])))
    T = pd.DataFrame(rows); T.round(4).to_csv(os.path.join(OUT, "F_souhrn_kotvy.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    x = T[(T.skupina == "vse") & (T.mereni == "P(dosazeni)")]
    print(x[["horizont", "T_prumer", "zrcadlo_prumer", "efekt_vyvazeny", "t", "efekt_2011_18", "efekt_2019_26"]].round(4).to_string())
    x = T[(T.skupina == "vse") & (T.mereni == "EV")]
    print(x[["horizont", "stop_atr", "T_prumer", "zrcadlo_prumer", "EV_na_sd", "efekt_vyvazeny", "t", "efekt_2011_18", "efekt_2019_26"]].round(3).to_string())
    x = T[(T.mereni == "P(dosazeni)") & (T.horizont == "1d")]
    print(x[["skupina", "T_prumer", "zrcadlo_prumer", "efekt_vyvazeny", "t"]].round(4).to_string())


if __name__ == "__main__":
    main()
