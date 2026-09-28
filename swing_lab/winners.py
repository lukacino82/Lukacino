"""
Which systems beat buy & hold - alone and in a group - and their equity curves.

Two levels, kept strictly apart:

  LEVEL 1  family ensembles: every variant of one idea (all thresholds x regimes x exits) is
           averaged with equal weight. No parameter is chosen, so there is no selection bias.
           A family that beats B&H here is a real candidate.

  LEVEL 2  single best variants. These ARE selected on the same history they are judged on, so
           their numbers are an upper bound, not an expectation. Reported for completeness and
           always flagged.

Comparison is on return of notional (percent), because 1 ES was ~70k USD in 2009 and ~390k USD in
2026 - counting points would flatter the later years. A system that is flat 85 % of the time cannot
beat B&H on total return, so the primary yardstick is risk-adjusted (Sharpe, MAR) plus alpha t-stat,
and the group test then shows what the same capital does when several roles are combined.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ensemble import EnsembleBook
from lab import Lab
from overlay import pct_series, stats
from sieve import RES, family as threshold_family

MIN_TRADES = 40


def family_key(setup: str) -> str:
    """blueprint id prefix: A01, B02, F03 ... everything else keeps its own name"""
    head = setup.split("_")[0]
    if len(head) == 3 and head[0].isalpha() and head[1:].isdigit():
        return head                      # blueprint id: A01, B02, F03 ...
    return threshold_family(setup)       # legacy setups: group thresholds, e.g. %b<# / RSI#<#


def main(cap=250, seed=7):
    lab = Lab()
    s0 = lab.start_i
    close = lab.d.close.values
    bh = pct_series(lab.bh, close)[s0:]
    bh_st = stats(bh, bh)
    g = pd.read_parquet(RES / "grid.parquet")
    g = g[(~g.exit.str.contains(r"\d+pt_")) & (g.trades >= MIN_TRADES)].copy()
    g["fam"] = g.setup.map(family_key)
    eb = EnsembleBook(lab)

    # ---------------- level 1: unbiased family ensembles ----------------
    rows, curves = [], {}
    for (fam, side), q in g.groupby(["fam", "side"]):
        qs = q.sample(min(cap, len(q)), random_state=seed)
        p, pos = eb.family_pnl(qs[["setup", "regime", "side", "exit"]])
        r = pct_series(p, close)[s0:]
        if r.std() == 0:
            continue
        st = stats(r, bh)
        st.update(family=fam, side=int(side), variants=len(q),
                  exposure=round(float((pos[s0:] != 0).mean()), 3),
                  trades_med=float(q.trades.median()))
        st["beats_sharpe"] = st["sharpe"] > bh_st["sharpe"]
        st["beats_mar"] = st["mar"] > bh_st["mar"]
        st["beats_cagr"] = st["cagr"] > bh_st["cagr"]
        rows.append(st)
        curves[f"{fam}|{side}"] = p
    fam_df = pd.DataFrame(rows).set_index(["family", "side"]).sort_values("alpha_t", ascending=False)
    fam_df.to_csv(RES / "winners_families.csv")

    # ---------------- level 2: single best variants (selection-biased) ----------------
    single = []
    for (fam, side), q in g.groupby(["fam", "side"]):
        best = None
        for r_ in q.nlargest(12, "sharpe").itertuples():
            p = eb.family_pnl(pd.DataFrame([{"setup": r_.setup, "regime": r_.regime, "side": r_.side,
                                             "exit": r_.exit}]))[0]
            rr = pct_series(p, close)[s0:]
            st = stats(rr, bh)
            st.update(family=fam, side=int(side), setup=r_.setup, regime=r_.regime, exit=r_.exit,
                      trades=int(r_.trades), win=round(float(r_.win), 3))
            if best is None or st["alpha_t"] > best["alpha_t"]:
                best = st
                bestp = p
        if best:
            best["beats_sharpe"] = best["sharpe"] > bh_st["sharpe"]
            single.append(best)
            curves[f"BEST {best['setup']}|{side}"] = bestp
    sng = pd.DataFrame(single).sort_values("alpha_t", ascending=False)
    sng.to_csv(RES / "winners_singles.csv", index=False)

    # ---------------- group books ----------------
    win = fam_df[(fam_df.alpha_t > 1.0) & (fam_df.index.get_level_values("side") > 0)]
    sel = list(win.index)
    grp = sum(curves[f"{f}|{s}"] for f, s in sel) / max(len(sel), 1)
    shorts = [i for i in fam_df.index if i[1] < 0]
    shortp = sum(curves[f"{f}|{s}"] for f, s in shorts) / max(len(shorts), 1) if shorts else np.zeros(lab.n)
    books = {
        "Buy & Hold 1 ES": lab.bh,
        f"Group: {len(sel)} long families (equal weight)": grp,
        "Group + short defense": grp + 0.5 * shortp,
        "Core B&H + group overlay 1x": lab.bh + grp,
        "Core B&H + group overlay 2x": lab.bh + 2 * grp,
    }
    book_st = {k: stats(pct_series(v, close)[s0:], bh) for k, v in books.items()}
    bdf = pd.DataFrame(book_st).T
    bdf.to_csv(RES / "winners_books.csv")

    # ---------------- equity curves (weekly samples, percent of notional, compounded) ----------------
    idx = lab.idx[s0:]
    wk = pd.Series(np.arange(len(idx)), index=idx).groupby(idx.to_period("W")).last().values
    cur = {"dates": [str(x.date()) for x in idx[wk]]}
    top = list(win.index)[:8]
    for f, s in top:
        r = pct_series(curves[f"{f}|{s}"], close)[s0:]
        cur[f] = [round(float(x), 4) for x in (np.cumprod(1 + r) - 1)[wk] * 100]
    for k, v in books.items():
        r = pct_series(v, close)[s0:]
        cur[k] = [round(float(x), 4) for x in (np.cumprod(1 + r) - 1)[wk] * 100]
    json.dump(cur, open(RES / "winners_curves.json", "w"))

    pd.set_option("display.width", 260)
    print("BUY & HOLD:", bh_st)
    cols = ["variants", "exposure", "cagr", "maxdd", "sharpe", "mar", "beta", "alpha_ann", "alpha_t",
            "beats_sharpe", "beats_mar", "beats_cagr"]
    print("\n=== LEVEL 1  family ensembles, no parameter selection (top 30 by alpha t) ===")
    print(fam_df[cols].head(30).to_string())
    print(f"\nfamilies beating B&H Sharpe: {int(fam_df.beats_sharpe.sum())} / {len(fam_df)}; "
          f"MAR: {int(fam_df.beats_mar.sum())}; CAGR: {int(fam_df.beats_cagr.sum())}")
    print("\n=== GROUP BOOKS ===")
    print(bdf.to_string())
    print("\n=== LEVEL 2  best single variant per family (SELECTION BIASED) ===")
    print(sng[["family", "setup", "regime", "exit", "trades", "win", "cagr", "maxdd", "sharpe", "mar",
               "alpha_t", "beats_sharpe"]].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
