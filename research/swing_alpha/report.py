"""Collect the SWING ALPHA results into out/report.html."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "out")


def r2(x, d=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    return None if not np.isfinite(x) else round(x, d)


def recs(df, d=3):
    return [{k: (r2(v, d) if not isinstance(v, (str, bool, np.bool_)) else (bool(v) if isinstance(v, (bool, np.bool_)) else v))
             for k, v in row.items()} for row in df.to_dict("records")]


def main():
    from features import load
    A = load()["audit"]
    E = pd.read_csv(os.path.join(OUT, "event_study.csv"))
    B = pd.read_csv(os.path.join(OUT, "experiment_b.csv"))
    C = pd.read_csv(os.path.join(OUT, "candidates.csv"))
    CT = pd.read_csv(os.path.join(OUT, "candidate_trades.csv"), parse_dates=["date"])
    WF = pd.read_csv(os.path.join(OUT, "walk_forward.csv"))
    WT = pd.read_csv(os.path.join(OUT, "walk_forward_trades.csv"))
    M = pd.read_csv(os.path.join(OUT, "markov.csv"), index_col=0)
    SM = pd.read_csv(os.path.join(OUT, "semi_markov.csv"))
    RR = pd.read_csv(os.path.join(OUT, "regime_runs.csv"), index_col=0)
    SH = pd.read_csv(os.path.join(OUT, "regime_share.csv"), index_col=0).iloc[:, 0]
    MP = {p: pd.read_csv(os.path.join(OUT, f"markov_{p}.csv"), index_col=0) for p in ("DISC", "VAL", "OOS")}
    rules = pd.read_csv(os.path.join(OUT, "candidate_rules.csv"), index_col=0).iloc[:, 0].to_dict()

    # Experiment A heat: t of excess by horizon
    heat = []
    for (fam, sig, side), g in E.groupby(["family", "signal", "side"], sort=False):
        g = g.set_index("h")
        heat.append(dict(family=fam, signal=sig, side=side, n=int(g.loc[5, "n"]),
                         t=[r2(g.loc[h, "t"], 2) for h in (1, 2, 3, 5, 7, 10, 20)],
                         ex5=r2(g.loc[5, "excess"]), ex10=r2(g.loc[10, "excess"]),
                         p5=[r2(g.loc[5, f"ex_{p}"]) for p in ("DISC", "VAL", "OOS")],
                         win5=r2(g.loc[5, "win"]), mfe5=r2(g.loc[5, "MFE"]), mae5=r2(g.loc[5, "MAE"])))
    # family-level edge (Experiment B)
    B["grp"] = np.where(B.family == "FADE", "fade (opačný směr)", np.where(B.family.isin(["SW01", "SW02", "SW03", "SW04", "H"]), "SW01–SW04 + H1–H5", "benchmarky"))
    fam = B[B.signal != "každý den"].groupby(["grp", "side"])[["edge_DISC", "edge_VAL", "edge_OOS"]].mean().reset_index()
    fam10 = B[(B.signal != "každý den") & (B.exit == "E01 čas 10D")].groupby(["grp", "side"])[["edge_DISC", "edge_VAL", "edge_OOS"]].mean().reset_index()
    sw_fam = B[B.family.isin(["SW01", "SW02", "SW03", "SW04", "H"])].groupby(["family", "side"])[["edge_DISC", "edge_VAL", "edge_OOS"]].mean().reset_index()
    rob = B[B.robust].sort_values("t_edge", ascending=False)[["family", "signal", "side", "exit", "n", "exp", "base_exp", "edge", "t_edge",
                                                              "win", "longest", "edge_DISC", "edge_VAL", "edge_OOS", "fdr"]]
    # DISC-only top selection and how it held up
    top_disc = B[B.n_DISC >= 40].sort_values("tedge_DISC", ascending=False).head(25)
    sel_stats = dict(n=len(top_disc), val_pos=r2((top_disc.edge_VAL > 0).mean()), oos_pos=r2((top_disc.edge_OOS > 0).mean()))
    # exits: averaged over all entries (long side) + every-day long grid
    ex = pd.read_csv(os.path.join(OUT, "exit_models.csv"))
    ex = ex[ex.side == "long"]
    ev = C[C.system == "každý den (long)"].set_index("exit")
    core = C[C.system == "jádro fade (long)"].set_index("exit")
    exits = []
    for _, r in ex.iterrows():
        e = r.exit
        exits.append(dict(exit=e, exp_all=r2(r.exp), edge_all=r2(r.edge), longest=r2(r.longest, 1), hold=r2(r.hold, 1),
                          every_exp=r2(ev.loc[e, "exp"]), every_win=r2(ev.loc[e, "win"]), every_longest=int(ev.loc[e, "longest"]),
                          every_pf=r2(ev.loc[e, "pf"]), core_exp=r2(core.loc[e, "exp"]), core_longest=int(core.loc[e, "longest"])))
    grid = []
    for s in (0.5, 1.0, 1.5, 2.0):
        for r in (1, 2, 3, 5):
            e = f"E06 SL {s} ATR · RRR {r}"
            grid.append(dict(sl=s, rr=r, exp=r2(ev.loc[e, "exp"]), win=r2(ev.loc[e, "win"]), longest=int(ev.loc[e, "longest"]),
                             hold=r2(ev.loc[e, "hold"], 1), core_exp=r2(core.loc[e, "exp"]), core_longest=int(core.loc[e, "longest"])))
    # candidates
    keep = ["E01 čas 5D", "E01 čas 10D", "E01 čas 20D", "E02 trailing 3.0 ATR", "E06 SL 2.0 ATR · RRR 3", "E06 SL 1.0 ATR · RRR 3", "E07 ½ na 1R + trailing"]
    cand = C[C.exit.isin(keep)][["system", "side", "exit", "n", "exp", "base_exp", "pts", "win", "pf", "longest", "maxdd", "t",
                                 "exp_DISC", "exp_VAL", "exp_OOS", "base_exp_DISC", "base_exp_VAL", "base_exp_OOS", "hold", "exposure", "exp_c2"]]
    # equity curves (points / 1 contract)
    curves = {}
    for ex_ in ("E01 čas 10D", "E01 čas 20D", "E06 SL 2.0 ATR · RRR 3"):
        for sysn in ("jádro fade (long)", "ansámbl fade (long)", "každý den (long)", "jádro fade (short)"):
            g = CT[(CT.system == sysn) & (CT.exit == ex_)].sort_values("date")
            curves[f"{sysn}|{ex_}"] = [[d.strftime("%Y-%m-%d"), r2(v, 1)] for d, v in zip(g.date, g.pts.cumsum())]
    wf_sum = WT.groupby("mode").pnl.agg(["count", "mean", "sum"]).reset_index()
    # SW04
    sm = {g: [[int(a), r2(p), r2(e, 2), int(n)] for a, p, e, n in zip(d.age, d.p_continue, d.exp_remaining, d.n)] for g, d in SM.groupby("regime")}
    data = dict(
        kpi=dict(days=4707, rules=int(E.groupby(["signal", "side"]).ngroups), combos=int(len(B)), fdr=int(B.fdr.sum()), robust=int(B.robust.sum()),
                 fdrA=int(E.fdr.sum())),
        audit={k: (v if isinstance(v, (str, int)) else str(v)) for k, v in A.items()},
        heat=heat, fam=recs(fam), fam10=recs(fam10), sw_fam=recs(sw_fam), rob=recs(rob), sel=sel_stats,
        exits=exits, grid=grid, cand=recs(cand), curves=curves, rules=rules,
        wf=recs(WF[WF["mode"] == "long+short"]), wf_sum=recs(wf_sum),
        markov=dict(states=list(M.index), m=[[r2(v) for v in row] for row in M.values],
                    diag={p: [r2(MP[p].loc[s, s]) for s in M.index] for p in MP}),
        runs={k: dict(n=int(RR.loc[k, "count"]), mean=r2(RR.loc[k, "mean"], 1), mx=int(RR.loc[k, "max"])) for k in M.index},
        share={k: r2(v) for k, v in SH.items()}, sm=sm)
    tpl = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    print("report", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
