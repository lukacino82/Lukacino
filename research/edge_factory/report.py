"""Build out/report.html for the Edge Factory."""
from __future__ import annotations

import json
import math
import os
import pickle

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


def r2(x, d=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, d)


IDEAS = [
    ("Obchodovat jen některé dny v týdnu (Po, Út–Čt, Pá…)", r"^Den v týdnu"),
    ("Liché / sudé dny", r"sudý|lichý"),
    ("Konkrétní den nebo obchodní den v měsíci", r"^Den v měsíci|obchodní den"),
    ("Měsíce, týdny v měsíci a jejich kombinace s dnem", r"^Měsíc|týden měsíce"),
    ("Londýnská seance 9–11 londýnského času (04–06 ET)", r"^Okno 0(?:4|5):"),
    ("Každá půlhodina dne, i v kombinaci s dnem v týdnu", r"^Okno"),
    ("VWAP retest: shora long, zdola short (D/W/M, RTH i globex)", r"retest"),
    ("Close za VWAP ±1/2/3σ", r"σ"),
    ("Objemové šoky a absorpce (velký objem, cena stojí)", r"^Objem|^Denní objem"),
    ("Divergence kumulativní delty od 1 h po 1 rok", r"CVD"),
    ("Stop-hunty kolem PDH/PDL, overnight, týdne, kulatých čísel", r"Stop-hunt"),
    ("Sekvence růstových a klesajících dní (chování davu)", r"Sekvence"),
    ("Gap a poloha openu vůči overnight a včerejšku", r"^Gap|^Open"),
    ("Přeprodanost: RSI(2), IBS", r"RSI|IBS"),
    ("Nová maxima/minima a drawdown od ATH", r"maximu|minimu|Drawdown"),
    ("Fáze Měsíce", r"Fáze Měsíce|Úplněk|Nov "),
    ("OPEX, quad witching, svátky, FOMC, přelom měsíce", r"OPEX|svátk|FOMC|Turn|Quad"),
    ("Opening drive (prvních 30 min RTH)", r"Prvních 30"),
]


def verdict(share_t2, holds):
    if share_t2 >= 7 and holds >= 58:
        return "info"
    if holds >= 56 and share_t2 >= 4.5:
        return "weak"
    return "noise"


def main():
    R = pd.read_csv(os.path.join(OUT, "factory_results.csv"))
    fam = pd.read_csv(os.path.join(OUT, "family_diag.csv"), index_col=0)
    # t histogram vs normal
    t = R.t_DISC.to_numpy()
    edges = np.arange(-5, 5.01, 0.25)
    h, _ = np.histogram(np.clip(t, -4.99, 4.99), edges)
    cdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    # factory t is |t| folded with the discovered direction -> positive; histogram of |t|
    at = np.abs(t)
    e2 = np.arange(0, 4.51, 0.25)
    ha, _ = np.histogram(np.clip(at, 0, 4.49), e2)
    expect = [len(at) * 2 * (cdf(e2[i + 1]) - cdf(e2[i])) for i in range(len(e2) - 1)]
    hist = dict(edges=e2.tolist(), counts=ha.tolist(), expect=[r2(x, 1) for x in expect])
    sc = R[["t_DISC", "t_LATER", "family"]].dropna().sample(min(1800, len(R)), random_state=3)
    scatter = [[r2(a), r2(b)] for a, b in zip(sc.t_DISC.abs(), sc.t_LATER)]
    # ideas table
    ideas = []
    for label, pat in IDEAS:
        x = R[R.name.str.contains(pat, regex=True)]
        if not len(x):
            continue
        s2 = (x.t_DISC.abs() > 2).mean() * 100
        holds = (x.ex_LATER > 0).mean() * 100
        b = x.loc[x.t_DISC.abs().idxmax()]
        ideas.append(dict(idea=label, n=len(x), share_t2=r2(s2, 1), holds=r2(holds, 0), verdict=verdict(s2, holds),
                          best=f"{b['name']} · {b.horizon} · {b.dir}", bt=[r2(b.t_DISC), r2(b.t_VAL), r2(b.t_TEST)]))
    cons = R[(R.t_DISC.abs() > 2) & (R.t_VAL > 1) & (R.t_TEST > 1)]
    consistent = [dict(name=r["name"], h=r.horizon, d=r.dir, n=int(r.n_DISC), t=[r2(r.t_DISC), r2(r.t_VAL), r2(r.t_TEST)],
                       ex=[r2(r.ex_DISC, 1), r2(r.ex_VAL, 1), r2(r.ex_TEST, 1)],
                       net=[r2(r.net_DISC, 1), r2(r.net_VAL, 1), r2(r.net_TEST, 1)]) for _, r in cons.iterrows()]
    famrows = [dict(f=i, **{k: r2(v, 1) for k, v in row.items()}) for i, row in fam.iterrows()]
    kpi = dict(tests=len(R), t2=int((R.t_DISC.abs() > 2).sum()), t2_exp=r2(len(R) * 2 * (1 - cdf(2)), 0),
               fdr=int(R.fdr.sum()), confirm=int(R.confirm.sum()), tradeable=int(R.tradeable.sum()))
    mi = pd.read_csv(os.path.join(OUT, "ml_intraday.csv"))
    md = pd.read_csv(os.path.join(OUT, "ml_daily.csv"))
    ms = pd.read_csv(os.path.join(OUT, "ml_daily_strategy.csv"))
    imp = pd.read_csv(os.path.join(OUT, "ml_importance.csv"), index_col=0).iloc[:, 0]
    ml = dict(intra=[dict(y=int(a.year), auc=r2(a.auc, 3), ic=r2(a.ic, 3), net=r2(a.net_bps), n=int(a.n)) for a in mi.itertuples()],
              daily=[dict(y=int(a.year), ic=r2(a.ic, 3), net=r2(a.net_bps, 1), n=int(a.n)) for a in md.itertuples()],
              strat=[{k: (r2(v) if not isinstance(v, str) else v) for k, v in row.items()} for row in ms.to_dict("records")],
              imp=[[k, r2(v, 0)] for k, v in imp.head(10).items()],
              intra_mean=dict(auc=r2(mi.auc.mean(), 3), ic=r2(mi.ic.mean(), 3), net=r2(mi.net_bps.mean())),
              daily_mean=dict(ic=r2(md.ic.mean(), 3), pos=int((md.ic > 0).sum()), years=len(md)))
    M = pickle.load(open(os.path.join(OUT, "money.pkl"), "rb"))
    tb = M["tables"]
    sel_wr = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60]
    sel_rr = [1, 2, 3, 5, 10, 15, 20]
    def tab(name):
        d = tb[name]
        return [[r2(d[R_][p], 3) if np.isfinite(d[R_][p]) else None for R_ in sel_rr] for p in sel_wr]
    money = dict(wr=sel_wr, rr=sel_rr, be={str(k): r2(v, 3) for k, v in tb["be"].items()}, ev=tab("ev"), kelly=tab("kelly"),
                 n2=tab("n2"), streak={str(k): {str(a): r2(b, 0) for a, b in v.items()} for k, v in tb["streak"].items()},
                 mc=M["mc"].to_dict("records"), real=M["real"], fin=M["fin"], dd=M["dd"],
                 wrbins=M["wr"].round(3).to_dict("records"), tbins=M["tt"].round(2).to_dict("records"),
                 rsi=M["rsi"].to_dict("records"),
                 curves={k: [[d.strftime("%Y-%m-%d"), r2(v, 3)] for d, v in s.items()] for k, s in M["curves"].items()})
    data = dict(kpi=kpi, hist=hist, scatter=scatter, ideas=ideas, consistent=consistent, fam=famrows, ml=ml, money=money)
    tpl = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=float))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    print("report", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
