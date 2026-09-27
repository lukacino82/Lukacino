"""
Pre-registered confirmation test on the never-seen ES window 2009-02 .. 2016-06
(results/preregistration_2008_2016.json). Nothing here was tuned on this window.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import systems as S
from canonical import canonical
from ensemble import EnsembleBook, stats_window
from lab import FRESH_END, Lab
from portfolio import run_portfolio
from sieve import RES

STRESS = 1.5 + 0.5  # 1.5 pt round trip + 1 tick slippage on entry and exit


def main():
    pre = json.load(open(RES / "preregistration_2008_2016.json"))
    lab = Lab(end=FRESH_END)
    s0, s1 = lab.start_i, lab.end_i
    bh = lab.bh[s0:s1]
    rows = []

    def single(name, cfg, calendar=False):
        out = {}
        for tag, cost in (("", 0.5), ("_stress", STRESS)):
            pnl, pos, tr = lab.run(dict(cfg, cost=cost))
            st = lab.stats(pnl, pos, tr)
            out[tag] = (st, pnl)
        st, pnl = out[""]
        sts = out["_stress"][0]
        nmin = pre["pass_rules_single"]["calendar_trades_min" if calendar else "trades_min"]
        ok = st["trades"] >= nmin and st["pf"] > 1.15 and sts["avg"] > 0
        rows.append(dict(name=name, trades=st["trades"], win=st["win"], avg=st["avg"], avg_stress=sts["avg"],
                         pf=st["pf"], total=st["total"], mdd=st["mdd"], sharpe=st["sharpe"], alpha_t=st["alpha_t"],
                         exposure=st["exposure"], passed=ok))
        return pnl

    canon = canonical(lab.d)
    cpnl = {}
    for k, cfg in canon.items():
        cpnl[k] = single(k, cfg, calendar=k.startswith(("C7", "C8", "C9")))
    setups = {s[0]: s for s in S.setups(lab.d)}
    exits = {e[0]: e for e in S.exits(lab.d)}
    reg = S.regimes(lab.d)
    apnl = {}
    for c in pre["candidates"]["audit_candidates"]:
        cfg = S.build_cfg(lab.d, setups[c["setup"]], exits[c["exit"]], 1, reg[c["regime"]], 0.5)
        apnl[c["id"]] = single(f'{c["id"]} {c["setup"]} [{c["regime"]}] {c["exit"]}', cfg, calendar=c["setup"].startswith("TOM"))
    # books
    books = {}
    books["Buy & Hold"] = lab.bh.copy()
    books["Long above SMA200 (T1)"] = cpnl["T1 Faber trend: long while C>SMA200"]
    books["Canonical book C1-C8"] = sum(v for k, v in cpnl.items() if k[:2] in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"))
    books["Audit candidates A1-A8"] = sum(apnl.values())
    for tag in ("full", "wf"):
        conf = json.load(open(RES / f"book_{tag}.json"))
        books[f"Legacy book_{tag}"] = run_portfolio(lab, conf)["total"]
    spec = {k: pd.DataFrame(v) for k, v in json.load(open(RES / "ensemble_spec_full.json")).items()}
    ens, _ = EnsembleBook(lab).book(spec)
    for k in ens.columns:
        books[f"Family: {k}"] = ens[k].values
    books["Family ensembles (5)"] = ens.sum(1).values
    brow = []
    ref = {n: stats_window(books[n][s0:s1], bh) for n in ("Buy & Hold", "Long above SMA200 (T1)")}
    for n, p in books.items():
        st = stats_window(p[s0:s1], bh)
        x = p[s0:s1]
        xm, bm = x.mean(), bh.mean()
        beta = ((x - xm) * (bh - bm)).sum() / ((bh - bm) ** 2).sum()
        res = x - beta * bh
        a_t = res.mean() / res.std() * np.sqrt(len(res))
        st.update(name=n, alpha_t=round(float(a_t), 2),
                  beats_bh=st["sharpe"] > ref["Buy & Hold"]["sharpe"],
                  beats_sma200=st["sharpe"] > ref["Long above SMA200 (T1)"]["sharpe"])
        brow.append(st)
    sd = pd.DataFrame(rows)
    bd = pd.DataFrame(brow)
    sd.to_csv(RES / "confirm_2008_singles.csv", index=False)
    bd.to_csv(RES / "confirm_2008_books.csv", index=False)
    yr = pd.DataFrame({k: pd.Series(v[s0:s1]).groupby(lab.years[s0:s1]).sum().values for k, v in books.items()
                       if not k.startswith("Family:")}, index=np.unique(lab.years[s0:s1]))
    yr.to_csv(RES / "confirm_2008_years.csv")
    pd.set_option("display.width", 250)
    print("window", lab.idx[s0].date(), "..", lab.idx[s1 - 1].date())
    print(sd.round(2).to_string())
    print(bd[["name", "total", "ann", "mdd", "sharpe", "mar", "beta", "alpha_t", "beats_bh", "beats_sma200"]].to_string())
    print(yr.round(0).T.to_string())


if __name__ == "__main__":
    main()
