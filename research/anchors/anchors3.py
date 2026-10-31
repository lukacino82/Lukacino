"""Anchors: mirror control balanced for drift. Anchor above price (toward = up) and anchor below (toward = down) have
opposite drift in T - A; the average of the two directions cancels the drift to first order. Week clusters."""
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


def main():
    f = P.load(); A = get_anchors(f); rng = np.random.default_rng(11)
    R = A2.make_events(f, A, False, rng); R["wk"] = A2.week_of(f, R)
    hit_r, net_r, _, _ = A2.outcomes(f, R)
    hit_m, net_m, _, _ = A2.outcomes(f, R, mirror=True)
    d = R["dir"].to_numpy(); blk = (R.wk.to_numpy() // 2)
    disc = f.ts.to_numpy()[R.i.to_numpy()] < np.datetime64("2019-01-01")
    cfg = R.anchor.to_numpy().astype(str) + "|" + R.bucket.to_numpy().astype(str)
    rows = []

    def balanced(x, mask):
        """drift-balanced effect = mean over (anchor above, anchor below) of the event mean, cluster-robust SE (2-week blocks)"""
        df = pd.DataFrame({"cfg": cfg[mask], "dir": d[mask], "blk": blk[mask], "x": x[mask].astype(np.float64)})
        g = df.groupby(["cfg", "dir"]).x
        df["mu"] = g.transform("mean"); df["n"] = g.transform("size")
        df["w"] = 0.5 / df.n
        eff = (df.w * df.x).groupby(df.cfg).sum()
        both = df.groupby("cfg").dir.nunique() == 2
        e = (df.w * (df.x - df.mu)).groupby([df.cfg, df.blk]).sum()
        se = np.sqrt((e ** 2).groupby(level=0).sum())
        return eff[both], se[both], df.groupby("cfg").size()[both]

    for h in A2.HNAMES:
        mets = {("P(dosazeni)", "-"): hit_r[h] - hit_m[h]}
        for s in A2.SNAMES:
            mets[("EV cisty b.", s if s else "bez stopu")] = net_r[(h, s)] - net_m[(h, s)]
        for (mer, s), diff in mets.items():
            eff, se, n = balanced(diff, np.ones(len(R), bool))
            e1, s1, n1 = balanced(diff, disc); e2, s2, n2 = balanced(diff, ~disc)
            for c in eff.index:
                an, bk = c.split("|")
                rows.append(dict(kotva=an, vzdalenost_atr=bk, horizont=h, mereni=mer, stop_atr=s, udalosti=int(n[c]),
                                 efekt_vyvazeny=eff[c], se=se[c], t=eff[c] / se[c] if se[c] > 0 else np.nan,
                                 efekt_2011_18=e1.get(c, np.nan), efekt_2019_26=e2.get(c, np.nan)))
    T = pd.DataFrame(rows)
    T.round(4).to_csv(os.path.join(OUT, "E_efekt_kotev_vyvazeny.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    for mer in ("P(dosazeni)", "EV cisty b."):
        x = T[T.mereni == mer]
        print(mer, "konfiguraci", len(x), " |t|>2:", (x.t.abs() > 2).mean().round(3), " t>2:", (x.t > 2).sum(), " t<-2:", (x.t < -2).sum(),
              " |t|>3:", (x.t.abs() > 3).sum(), " prumerny efekt:", x.efekt_vyvazeny.mean().round(4))
    x = T[T.mereni == "P(dosazeni)"]
    print(x.groupby("horizont").efekt_vyvazeny.agg(["mean", "std"]).round(4))
    print(x.groupby("kotva").agg(efekt=("efekt_vyvazeny", "mean"), t=("t", "mean"), pod_t2=("t", lambda s: (s.abs() > 2).mean())).round(3))
    print(x.sort_values("t", ascending=False).head(10).round(3).to_string())
    c = T[(T.mereni == "P(dosazeni)")].dropna(subset=["efekt_2011_18", "efekt_2019_26"])
    print("stabilita (P dosazeni): corr efekt 2011-18 vs 2019-26:", c.efekt_2011_18.corr(c.efekt_2019_26).round(3),
          " stejne znamenko:", ((c.efekt_2011_18 * c.efekt_2019_26) > 0).mean().round(3))


if __name__ == "__main__":
    main()
