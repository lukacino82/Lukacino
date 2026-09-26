"""
Family ensembles - the robust answer to the winner's curse.

Picking the single best of thousands of variants overfits (proved walk-forward in README).
Instead a *family* (one trading idea, e.g. "IBS below x") is accepted only when the large
majority of ALL its variants (thresholds x regimes x exits) is profitable in every sub-period,
and it is traded as an equal-weight ensemble of its qualifying variants. One family = one
ES-equivalent of risk, split over the variants (fractions are executed with MES micro
contracts: 1 ES = 10 MES).

Walk-forward protocol:
  selection uses grid_wf.parquet (data until 2021-12-31, sub-periods 2016-18 / 2019-20H1 / 2020H2-21)
  the resulting book is traded blind on 2022-01-01 .. 2026-09-23.

usage: python ensemble.py [--wf]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

import systems as S
from lab import Lab
from sieve import RES, deflated_sharpe, family

LT_LONG = {"c>sma200", "sma50>sma200", "c>sma200&dd<10"}
FAMILY_RULES = dict(min_variants=50, min_share_positive=0.75, min_median_pf=1.3)
VARIANT_RULES = dict(trades=20, pf=1.15)


def prepare(g: pd.DataFrame) -> pd.DataFrame:
    g = g[~g.exit.str.contains(r"\d+pt_")].copy()          # scale invariant exits only
    g = g[g.side > 0]                                         # shorts failed in every family
    g["family"] = g.setup.map(family)
    g["rclass"] = np.where(g.regime.isin(LT_LONG), "LT_bull", "short_term")
    return g


def family_table(g: pd.DataFrame) -> pd.DataFrame:
    f = g.groupby(["family", "rclass"]).agg(
        n=("total", "size"),
        pos_disc=("disc_ann", lambda x: (x > 0).mean()),
        pos_val=("val_ann", lambda x: (x > 0).mean()),
        pos_oos=("oos_ann", lambda x: (x > 0).mean()),
        med_pf=("pf", "median"), med_sharpe=("sharpe", "median"), med_expo=("exposure", "median"))
    f["min_share"] = f[["pos_disc", "pos_val", "pos_oos"]].min(1)
    r = FAMILY_RULES
    f["accepted"] = (f.n >= r["min_variants"]) & (f.min_share >= r["min_share_positive"]) & (f.med_pf >= r["min_median_pf"])
    return f.sort_values("min_share", ascending=False)


def variants(g: pd.DataFrame, fam, rclass):
    v = g[(g.family == fam) & (g.rclass == rclass)]
    r = VARIANT_RULES
    return v[(v.trades >= r["trades"]) & (v.pf >= r["pf"]) & (v.disc_ann > 0) & (v.val_ann > 0) & (v.oos_ann > 0)]


class EnsembleBook:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.setups = {s[0]: s for s in S.setups(lab.d)}
        self.exits = {e[0]: e for e in S.exits(lab.d)}
        self.reg = S.regimes(lab.d)

    def family_pnl(self, rows: pd.DataFrame, cost=0.5):
        tot = np.zeros(self.lab.n)
        pos = np.zeros(self.lab.n)
        for r in rows.itertuples():
            cfg = S.build_cfg(self.lab.d, self.setups[r.setup], self.exits[r.exit], int(r.side), self.reg[r.regime], cost)
            p, ps, _ = self.lab.run(cfg)
            tot += p
            pos += np.abs(ps)
        k = max(len(rows), 1)
        return tot / k, pos / k

    def book(self, spec: dict, cost=0.5):
        cols = {}
        expo = {}
        for fam_key, rows in spec.items():
            cols[fam_key], expo[fam_key] = self.family_pnl(rows, cost)
        return pd.DataFrame(cols, index=self.lab.idx), pd.DataFrame(expo, index=self.lab.idx)


def build_spec(g: pd.DataFrame):
    ft = family_table(g)
    spec = {}
    for (fam, rc), row in ft[ft.accepted].iterrows():
        v = variants(g, fam, rc)
        if len(v) >= 5:
            spec[f"{fam} [{rc}]"] = v[["setup", "regime", "side", "exit"]]
    return ft, spec


def stats_window(x, bh):
    eq = np.cumsum(x)
    mdd = float((np.maximum.accumulate(np.maximum(eq, 0)) - eq).max())
    sh = x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0
    b = np.cov(x, bh)[0, 1] / bh.var()
    res = x - b * bh
    ir = res.mean() / res.std() * np.sqrt(252) if res.std() > 0 else 0
    return dict(total=round(float(eq[-1]), 1), ann=round(float(eq[-1]) / (len(x) / 252), 1), mdd=round(mdd, 1),
                sharpe=round(float(sh), 2), mar=round(float(eq[-1]) / (len(x) / 252) / mdd, 2) if mdd > 0 else 0,
                beta=round(float(b), 2), alpha_ir=round(float(ir), 2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", action="store_true")
    a = ap.parse_args()
    tag = "wf" if a.wf else "full"
    g = prepare(pd.read_parquet(RES / ("grid_wf.parquet" if a.wf else "grid.parquet")))
    ft, spec = build_spec(g)
    ft.to_csv(RES / f"families_{tag}.csv")
    print(ft.head(30).round(2).to_string())
    print("accepted families:", {k: len(v) for k, v in spec.items()})
    lab = Lab()
    eb = EnsembleBook(lab)
    pnl, expo = eb.book(spec)
    pnl.to_parquet(RES / f"ensemble_pnl_{tag}.parquet")
    json.dump({k: v.to_dict("records") for k, v in spec.items()}, open(RES / f"ensemble_spec_{tag}.json", "w"), indent=1)
    tot = pnl.sum(1).values
    s0 = lab.start_i
    for name, m in [("full 2017-2026", lab.idx >= lab.idx[s0]), ("blind 2022-2026", lab.idx >= "2022-01-01"),
                    ("2022 bear", (lab.idx >= "2022-01-01") & (lab.idx < "2023-01-01")),
                    ("2023-2026", lab.idx >= "2023-01-01")]:
        print(f"{name:16s} BOOK {stats_window(tot[m], lab.bh[m])}\n{'':16s} B&H  {stats_window(lab.bh[m], lab.bh[m])}"
              f"\n{'':16s} CORE+SAT {stats_window(tot[m] + lab.bh[m], lab.bh[m])}")
    print("avg ES-equivalent exposure", round(float(expo.sum(1)[s0:].mean()), 2), "families", pnl.shape[1])
    print(pnl[lab.idx >= "2022-01-01"].groupby(lab.idx[lab.idx >= "2022-01-01"].year).sum().round(0).T)
    print(pnl.iloc[s0:].corr().round(2))
