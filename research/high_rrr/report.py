"""Collect the high-RRR results into out/report.html."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


def r2(x, d=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    return None if not np.isfinite(x) else round(x, d)


def recs(df, d=3):
    return [{k: r2(v, d) if not isinstance(v, str) else v for k, v in row.items()} for row in df.to_dict("records")]


def main():
    base = pd.read_csv(os.path.join(OUT, "baseline_grid.csv"))
    sf = pd.read_csv(os.path.join(OUT, "streak_freq.csv"))
    sc = pd.read_csv(os.path.join(OUT, "streak_context.csv"))
    sy = pd.read_csv(os.path.join(OUT, "streak_years.csv"))
    sa = pd.read_csv(os.path.join(OUT, "sl_vs_atr.csv"))
    ve = pd.read_csv(os.path.join(OUT, "var_effects_side.csv"))
    tt = pd.read_csv(os.path.join(OUT, "tests_table.csv"))
    ex = pd.read_csv(os.path.join(OUT, "exit_variants.csv"))
    pr = pd.read_csv(os.path.join(OUT, "pause_rules.csv"))
    R = pd.read_parquet(os.path.join(OUT, "search_real.parquet"))
    N = pd.read_parquet(os.path.join(OUT, "search_null1.parquet"))

    # clustering summary from the baseline grid
    cl = base[base.rr.isin([3, 5, 10, 20]) & base.sl.isin([10, 20, 30])][
        ["name", "hz", "sl", "rr", "n_ALL", "loss_ALL", "longest_ALL", "exp_longest_iid_ALL", "cluster_ALL", "exp_DISC", "exp_VAL", "exp_TEST"]]

    def cnt(X, td, tl):
        ok = ((X.t_DISC >= td) & (X.t_VAL >= tl) & (X.t_TEST >= tl) & (X.n_VAL >= 15) & (X.n_TEST >= 15) & (X.filt != "(bez filtru)")
              & (X.exp_DISC > X.base_exp_DISC) & (X.exp_VAL > X.base_exp_VAL) & (X.exp_TEST > X.base_exp_TEST))
        return int(X[ok].groupby(["entry", "filt"]).ngroups), ok
    thr = []
    for td, tl in ((2, 0), (2, 0.5), (2, 1), (2.5, 1), (3, 1)):
        a, ok = cnt(R, td, tl)
        b, _ = cnt(N, td, tl)
        thr.append(dict(td=td, tl=tl, real=a, null=b))
    _, ok = cnt(R, 2, 1)
    top = R[ok].sort_values("t_TEST", ascending=False).drop_duplicates(["entry", "filt"]).head(20)
    top = top[["entry", "filt", "hz", "sl", "rr", "n_DISC", "n_VAL", "n_TEST", "exp_DISC", "exp_VAL", "exp_TEST", "t_DISC", "t_VAL", "t_TEST",
               "win_ALL", "base_win_ALL", "longest_ALL"]]
    # strongest consistent context effects, by side
    ve = ve[ve.win_consistent | ve.exp_consistent].copy()
    ve = ve[ve.n_cfg >= 300]
    sa_p = sa[sa.rr == 10].pivot_table(index="ratio", columns="sl", values="stop").reset_index()
    order = ["0-0.1", "0.1-0.2", "0.2-0.35", "0.35-0.6", "0.6-1.0", "1.0-9"]
    sa_p["o"] = sa_p.ratio.map({k: i for i, k in enumerate(order)})
    sa_p = sa_p.sort_values("o").drop(columns="o")
    sa_agg = sa[sa.rr == 10].groupby("ratio").apply(lambda g: np.average(g.stop, weights=g.n)).reindex(order).dropna()
    years = sy.pivot_table(index="year", columns="config", values="streak_trades", aggfunc="sum").fillna(0)
    ytr = sy.pivot_table(index="year", columns="config", values="trades", aggfunc="sum").fillna(0)
    cf = pd.read_csv(os.path.join(OUT, "corr_filter.csv"))
    a = cf[cf.filt == "bez filtru"].reset_index(drop=True); b = cf[cf.filt != "bez filtru"].reset_index(drop=True)
    dd = pd.DataFrame({"entry": a.entry, "loss_a": a.loss, "loss_b": b.loss, "longest_a": a.longest, "longest_b": b.longest,
                       "k_a": a.ge10_per1000, "k_b": b.ge10_per1000, "exp_a": a.exp, "exp_b": b.exp,
                       "short": b.longest <= a.longest, "fewer": b.ge10_per1000 < a.ge10_per1000,
                       "better": (b.exp_DISC > a.exp_DISC) & (b.exp_VAL > a.exp_VAL) & (b.exp_TEST > a.exp_TEST)})
    corr = dd.groupby("entry").mean(numeric_only=True).reset_index()
    data = dict(corr=recs(corr),
        kpi=dict(entries=186135, sims=int(186135 * 10 * 9 * 2), combos=int(len(R)), null=int(len(N))),
        cl=recs(cl), sf=recs(sf, 2), sc=recs(sc), sa_agg=[[k, r2(v)] for k, v in sa_agg.items()],
        years=dict(index=[int(i) for i in years.index], cols=list(years.columns),
                   share={c: [r2(years.loc[y, c] / max(ytr.loc[y, c], 1)) for y in years.index] for c in years.columns}),
        ve=recs(ve.reset_index() if "side" not in ve.columns else ve), tt=recs(tt), thr=thr, top=recs(top), ex=recs(ex), pr=recs(pr))
    tpl = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=float))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    print("report", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
