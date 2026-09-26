"""Build the self-contained HTML report (out/report.html) from the result files."""
from __future__ import annotations

import json
import os
import pickle

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
COST = 0.5
PER = ["DISC 2018-22", "VAL 2023-24", "OOS 2025-26"]
GATES = ["G1 net>0 @0.5 a @1.0 b.", "G2 kladná ve DISC/VAL/OOS", "G3 kladná v PRE 2016-18",
         "G4 edge vs. náhodný long t>=2", "G5 plató TP/SL >=60 %", "G6 walk-forward > 0", "G7 parita (Excel data) > 0"]


def r(x, d=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), d)


def main():
    summ = pd.read_csv(os.path.join(OUT, "summary.csv"))
    meta = json.load(open(os.path.join(OUT, "meta.json")))
    ser = pickle.load(open(os.path.join(OUT, "series.pkl"), "rb"))
    eq, port, bench, rnorm = ser["eq"], ser["port"], ser["bench"], ser["rnorm"]

    strats = []
    for _, s in summ.iterrows():
        e = eq.get(s.strategy)
        pts = [] if e is None else [[d.strftime("%Y-%m-%d"), r(v, 1)] for d, v in zip(e.date, e.net.cumsum())]
        strats.append(dict(
            name=s.strategy, phase=s.phase, rule=s.rule, exit=s.exit, n=int(s.n), exp=r(s.exp), exps=r(s.exp_stress),
            pf=r(s.pf), dd=r(s.maxdd, 0), net=r(s.net, 0), tedge=r(s.t_edge), edge=r(s.edge), nullexp=r(s.null_exp),
            per=[r(s[f"exp|{p}"]) for p in PER], pre_n=int(s.pre_n), pre=r(s.pre_exp), xl=r(s.xl_exp),
            plateau=r(s.plateau), wf=r(s.wf_net, 0), gates=[bool(s[g]) for g in GATES], passed=int(s.gates_passed),
            verdict=s.verdict, eq=pts,
            R=[r(rnorm.loc[s.strategy].get(p), 3) if s.strategy in rnorm.index else None for p in PER]))

    b = bench.resample("W-FRI").last().dropna()
    bench_js = dict(bh=[[d.strftime("%Y-%m-%d"), r(v, 0)] for d, v in b.buy_hold.items()],
                    rth=[[d.strftime("%Y-%m-%d"), r(v, 0)] for d, v in b.rth_long_open_close.items()])
    port_js = [[d.strftime("%Y-%m-%d"), r(v, 1)] for d, v in port.cumsum().items()]

    o = pd.read_csv(os.path.join(OUT, "openx.csv"))
    rr = [(10, 10), (10, 15), (15, 10), (20, 10), (30, 10), (20, 20), (20, 30), (30, 20), (40, 20), (60, 20)]
    heat = {}
    for mode in ("fade", "break"):
        for side in ("long", "short"):
            q = o[(o.src == "es1m") & (o.unit == "pts") & (o["mode"] == mode) & (o.side == side)]
            heat[f"{mode}_{side}"] = [[dict(exp=r(q[(q.X == X) & (q.tp == tp) & (q.sl == sl)].exp.iloc[0]),
                                            t=r(q[(q.X == X) & (q.tp == tp) & (q.sl == sl)].t.iloc[0]),
                                            n=int(q[(q.X == X) & (q.tp == tp) & (q.sl == sl)].n.iloc[0]),
                                            tpr=r(q[(q.X == X) & (q.tp == tp) & (q.sl == sl)].tp_rate.iloc[0], 3))
                                       for tp, sl in rr] for X in (10, 15, 20, 40)]
    ox_all = dict(n=len(o), max_t=r(o.t.max()), pos=int((o.exp > 0).sum()))
    base = o[(o.src == "es1m") & (o.unit == "pts") & (o.X == 20) & (o.tp == 15) & (o.sl == 10) & (o["mode"] == "fade")]
    base_js = {row.side: dict(n=int(row.n), fill=r(row.fill_rate, 3), tpr=r(row.tp_rate, 3), slr=r(row.sl_rate, 3),
                              exp=r(row.exp), net=r(row.net, 0)) for row in base.itertuples()}

    rg = pd.read_csv(os.path.join(OUT, "ranges.csv"))
    x = rg[rg.src == "es1m"].range.dropna().to_numpy()
    edges = np.arange(0, 205, 5)
    h, _ = np.histogram(np.clip(x, 0, 200 - 1e-9), edges)
    hist = dict(edges=edges.tolist(), counts=h.tolist(), over=int((x >= 200).sum()))
    ranges = meta["ranges"]

    data = dict(strats=strats, bench=bench_js, port=port_js, portstats=meta["portfolio"], watch=meta["watch"],
                yard=meta["yard"], heat=heat, rr=[f"{a}/{b}" for a, b in rr], ox=ox_all, base=base_js, hist=hist,
                ranges=ranges, corr=meta["corr"])
    tpl = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    print("report.html", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
