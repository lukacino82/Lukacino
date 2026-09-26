"""
Pick a diversified multi-swing book from the sieve survivors and prove it walk-forward.

  1. stage-3 robust systems ranked by composite score
  2. greedy diversification: one system per setup family, daily-P&L correlation < MAX_CORR
     with everything already in the book, at most MAX_SYSTEMS
  3. book statistics vs Buy & Hold, Deflated Sharpe of the book
  4. walk-forward: the same procedure run on 2016-2021 only (grid_wf.parquet), the chosen book
     is then traded blind on 2022-2026

usage: python select_portfolio.py            (full-sample selection  -> results/book_full.json)
       python select_portfolio.py --wf       (walk-forward selection -> results/book_wf.json)
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from lab import Lab
from sieve import RES, Sieve, deflated_sharpe, score

MAX_CORR = 0.35
MAX_SYSTEMS = 8


def select(sv: Sieve, n_top=600):
    g = sv.g
    c2 = g[g.s2].copy()
    c2["score"] = score(c2)
    top = c2.sort_values("score", ascending=False).groupby(["setup", "regime", "side"]).head(2).head(n_top)
    n_eff = g.groupby(["setup", "regime", "side"]).ngroups
    s3 = sv.stage3(top, n_trials=n_eff)
    rob = s3[s3.s3].sort_values("score", ascending=False)
    book, pnls, fams = [], [], set()
    lab = sv.lab
    for _, r in rob.iterrows():
        if r.family in fams:
            continue
        pnl, _, _ = lab.run(sv.cfg(r))
        p = pnl[lab.start_i:lab.end_i]
        if pnls and max(abs(np.corrcoef(p, q)[0, 1]) for q in pnls) >= MAX_CORR:
            continue
        book.append(r)
        pnls.append(p)
        fams.add(r.family)
        if len(book) >= MAX_SYSTEMS:
            break
    return pd.DataFrame(book), s3, n_eff


def book_to_config(book: pd.DataFrame):
    return {"cost_pts": 0.5, "max_contracts": None, "systems": [
        {"id": f"S{i + 1}_{r.setup}", "enabled": "yes", "contracts": 1, "setup": r.setup,
         "regime": r.regime, "side": int(r.side), "exit": r.exit} for i, r in enumerate(book.itertuples())]}


if __name__ == "__main__":
    from portfolio import run_portfolio

    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", action="store_true")
    a = ap.parse_args()
    sv = Sieve("grid_wf.parquet" if a.wf else "grid.parquet", wf=a.wf)
    book, s3, n_eff = select(sv)
    tag = "wf" if a.wf else "full"
    s3.to_parquet(RES / f"stage3_{tag}.parquet")
    conf = book_to_config(book)
    (RES / f"book_{tag}.json").write_text(json.dumps(conf, indent=2))
    cols = ["setup", "regime", "exit", "trades", "win", "avg", "pf", "sharpe", "mar", "alpha_t", "exposure", "dsr"]
    print(f"robust stage-3: {int(s3.s3.sum())} / {len(s3)}")
    print(book[cols].to_string())
    full = Lab()
    res = run_portfolio(full, conf)
    st = res["stats"]
    p = res["total"][full.start_i:]
    dsr = deflated_sharpe(st["sharpe"], len(p), float(pd.Series(p).skew()), float(pd.Series(p).kurt() + 3),
                          n_eff, sv.g.sharpe.var())
    keys = ["total", "ann", "mdd", "sharpe", "sortino", "mar", "alpha_t", "beta", "exposure", "trades", "win", "pf",
            "disc_ann", "val_ann", "oos_ann", "years_pos", "worst_year"]
    print("BOOK", {k: round(float(st[k]), 2) for k in keys}, "DSR", round(dsr, 3))
    print("B&H ", {k: round(float(full.bh_stats[k]), 2) for k in keys if k in full.bh_stats})
    if a.wf:
        m = full.idx >= "2022-01-01"
        bk = res["total"][m]
        bh = full.bh[m]
        def s_(x):
            eq = np.cumsum(x)
            return dict(total=round(eq[-1], 1), mdd=round(float((np.maximum.accumulate(np.maximum(eq, 0)) - eq).max()), 1),
                        sharpe=round(x.mean() / x.std() * np.sqrt(252), 2))
        print("BLIND 2022-2026  book", s_(bk), " B&H", s_(bh), " core+sat", s_(bk + bh))
