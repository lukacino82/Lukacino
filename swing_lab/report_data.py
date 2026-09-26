"""Collect every number the HTML report shows into results/report_data.json."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from canonical import run_all
from ensemble import stats_window
from lab import Lab
from portfolio import run_portfolio
from sieve import RES


def main():
    lab = Lab()
    s0 = lab.start_i
    idx = lab.idx[s0:]
    wk = pd.Series(np.arange(len(idx)), index=idx).groupby(idx.to_period("W")).last().values  # weekly samples
    dates = [str(x.date()) for x in idx[wk]]

    def curve(p):
        return [round(float(v), 1) for v in np.cumsum(p[s0:])[wk]]

    st, pnl, _ = run_all(lab)
    C = [c for c in pnl.columns if c.startswith("C")]
    canon_book = pnl[[c for c in C if not c.startswith("C9")]].sum(1).values
    full_book = run_portfolio(lab, json.load(open(RES / "book_full.json")))["total"]
    wf_book = run_portfolio(lab, json.load(open(RES / "book_wf.json")))["total"]
    m22 = lab.idx >= "2022-01-01"
    i22 = int(np.argmax(m22))
    wk22 = pd.Series(np.arange(i22, lab.n), index=lab.idx[i22:]).groupby(lab.idx[i22:].to_period("W")).last().values

    def curve22(p):
        return [round(float(v), 1) for v in np.cumsum(p[i22:])[wk22 - i22]]

    fams = pd.read_csv(RES / "families_full.csv") if (RES / "families_full.csv").exists() else None
    g = pd.read_parquet(RES / "grid.parquet")
    funnel = json.load(open(RES / "funnel.json")) if (RES / "funnel.json").exists() else None
    out = {
        "dates": dates,
        "bh": curve(lab.bh), "canon_book": curve(canon_book), "insample_book": curve(full_book),
        "dates22": [str(x.date()) for x in lab.idx[wk22]],
        "wf_book22": curve22(wf_book), "bh22": curve22(lab.bh),
        "canon": [{"name": k, **{c: (None if pd.isna(v) else round(float(v), 3)) for c, v in st.loc[k].items()}}
                  for k in st.index],
        "canon_curves": {k: curve(pnl[k].values) for k in pnl.columns},
        "stats": {
            "bh": stats_window(lab.bh[s0:], lab.bh[s0:]),
            "canon_book": stats_window(canon_book[s0:], lab.bh[s0:]),
            "insample_book": stats_window(full_book[s0:], lab.bh[s0:]),
            "wf_book_blind": stats_window(wf_book[m22], lab.bh[m22]),
            "bh_blind": stats_window(lab.bh[m22], lab.bh[m22]),
            "canon_2022": stats_window(canon_book[m22 & (lab.idx < "2023-01-01")], lab.bh[m22 & (lab.idx < "2023-01-01")]),
        },
        "n_tested": int(len(g)), "n_long": int((g.side > 0).sum()), "n_short": int((g.side < 0).sum()),
    }
    json.dump(out, open(RES / "report_data.json", "w"))
    print({k: v for k, v in out["stats"].items()})


if __name__ == "__main__":
    main()
