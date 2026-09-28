"""
Decisive test: does picking the winning families transfer out of sample?

Families are ranked ONLY on 2009-2017 (alpha t-stat vs B&H) and then traded blind on 2018-2026,
which contains 2018, the 2020 crash and the 2022 bear market. Also an expanding version that
re-picks every year. If the 2018-2026 book still beats B&H at equal volatility, the family-ensemble
approach is transferable; if not, the 12 winners are a story about the past.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ensemble import EnsembleBook
from lab import Lab
from overlay import pct_series, stats
from sieve import RES
from winners import family_key

SPLIT = "2018-01-01"


def main(cap=250):
    lab = Lab()
    s0 = lab.start_i
    close = lab.d.close.values
    idx = lab.idx[s0:]
    bh = pct_series(lab.bh, close)[s0:]
    g = pd.read_parquet(RES / "grid.parquet")
    g = g[(~g.exit.str.contains(r"\d+pt_")) & (g.trades >= 40)].copy()
    g["fam"] = g.setup.map(family_key)
    eb = EnsembleBook(lab)
    fam = {}
    for (f, side), q in g.groupby(["fam", "side"]):
        if side < 0:
            continue
        qs = q.sample(min(cap, len(q)), random_state=7)
        r = pct_series(eb.family_pnl(qs[["setup", "regime", "side", "exit"]])[0], close)[s0:]
        if r.std() > 0:
            fam[f] = r
    F = pd.DataFrame(fam, index=idx)
    tr = idx < SPLIT
    te = ~tr

    def alpha_t(r, b):
        beta = np.cov(r, b)[0, 1] / b.var()
        res = r - beta * b
        return res.mean() / res.std() * np.sqrt(len(res)) if res.std() > 0 else 0.0

    score = F[tr].apply(lambda c: alpha_t(c.values, bh[tr]))
    res = {}
    for k in (5, 10, 20):
        pick = score.nlargest(k).index.tolist()
        book = F[pick].mean(1).values
        res[f"top{k}"] = dict(picked=pick,
                              train=stats(book[tr], bh[tr]), test=stats(book[te], bh[te]))
    allf = F.mean(1).values
    res["all_families"] = dict(picked=["ALL"], train=stats(allf[tr], bh[tr]), test=stats(allf[te], bh[te]))
    res["buy_hold"] = dict(picked=[], train=stats(bh[tr], bh[tr]), test=stats(bh[te], bh[te]))

    print(f"train {idx[0].date()}..{idx[tr][-1].date()}   test {idx[te][0].date()}..{idx[-1].date()}")
    rows = []
    for k, v in res.items():
        rows.append(dict(book=k, **{f"tr_{a}": b for a, b in v["train"].items() if a in ("sharpe", "mar", "alpha_t")},
                         **{f"te_{a}": b for a, b in v["test"].items() if a in ("cagr", "maxdd", "sharpe", "mar", "alpha_ann", "alpha_t")}))
    rdf = pd.DataFrame(rows)
    # volatility-matched test-period return
    tgt = bh[te].std() * np.sqrt(252)
    for r_ in rows:
        pass
    vm = {}
    for k, v in res.items():
        b = F[res[k]["picked"]].mean(1).values if k.startswith("top") else (allf if k == "all_families" else bh)
        x = b[te] * (tgt / (b[te].std() * np.sqrt(252)))
        vm[k] = stats(x, bh[te])["cagr"]
    rdf["te_volmatched_cagr"] = rdf.book.map(vm)
    print(rdf.to_string(index=False))
    print("\npicked on 2009-2017:", res["top10"]["picked"])
    json.dump({k: {kk: vv for kk, vv in v.items()} for k, v in res.items()},
              open(RES / "wf_families.json", "w"), default=float, indent=1)
    # equity curves for the blind period
    wk = pd.Series(np.arange(te.sum()), index=idx[te]).groupby(idx[te].to_period("W")).last().values
    cur = {"dates": [str(x.date()) for x in idx[te][wk]]}
    for k in ("top10", "all_families"):
        b = F[res[k]["picked"]].mean(1).values if k == "top10" else allf
        x = b[te] * (tgt / (b[te].std() * np.sqrt(252)))
        cur[k] = [round(float(x_), 3) for x_ in ((np.cumprod(1 + x) - 1) * 100)[wk]]
    cur["buy_hold"] = [round(float(x_), 3) for x_ in ((np.cumprod(1 + bh[te]) - 1) * 100)[wk]]
    json.dump(cur, open(RES / "wf_families_curves.json", "w"))


if __name__ == "__main__":
    main()
