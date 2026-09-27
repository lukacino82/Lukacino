"""Numbers for report v2 (ES2008 feed, 18 years): confirmation, protocol funnel, families, overlays."""
import json

import numpy as np
import pandas as pd

from canonical import canonical
from ensemble import EnsembleBook
from lab import Lab
from sieve import RES
import protocol_sieve as P


def pct_stats(r, b):
    eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (252 / len(r)) - 1
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    beta = np.cov(r, b)[0, 1] / b.var()
    res = r - beta * b
    ir = res.mean() / res.std() * np.sqrt(252)
    return dict(cagr=round(cagr * 100, 1), maxdd=round(dd * 100, 1), sharpe=round(r.mean() / r.std() * np.sqrt(252), 2),
                beta=round(beta, 2), alpha_t=round(ir * np.sqrt(len(r) / 252), 2))


def main():
    lab = Lab()
    s0 = lab.start_i
    c = lab.d.close.values
    prev = np.r_[np.nan, c[:-1]]
    g = P.rules(P.load())
    eb = EnsembleBook(lab)
    can = canonical(lab.d)
    runs = {k[:2]: lab.run(dict(v, cost=0.5))[0] for k, v in can.items()}

    def fam(prefix, reg, side):
        rows = g[g.setup.str.startswith(prefix) & (g.regime == reg) & (g.side == side)][["setup", "regime", "side", "exit"]]
        return eb.family_pnl(rows)[0]

    hedge = fam("S_Breakdown20dLow_bear", "sma50<sma200", -1) + fam("S_VolExp_LostPrevWeekLow", "sma50<sma200", -1)
    core = sum(runs[k] for k in ("C1", "C2", "C3", "C4", "C5", "C6"))
    hi20 = fam("P_Hi20DD", "c>sma200", 1)
    books = {"Buy & Hold 1 ES": lab.bh, "Long nad SMA200 (T1)": runs["T1"], "Kniha C1–C6": core,
             "B&H + kniha C1–C6 (1/6)": lab.bh + core / 6, "B&H + short modul": lab.bh + hedge,
             "C1–C6 + Hi20DD rodina + shorty": core + hi20 + hedge}
    m = np.arange(lab.n) > s0
    pct = {k: pct_stats((v / prev)[m], (lab.bh / prev)[m]) for k, v in books.items()}
    for k in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"):
        pct[k] = pct_stats((runs[k] / prev)[m], (lab.bh / prev)[m])
    idx = lab.idx[s0:]
    wk = pd.Series(np.arange(len(idx)), index=idx).groupby(idx.to_period("W")).last().values
    curves = {k: [round(float(x), 1) for x in np.cumsum(v[s0:])[wk]] for k, v in
              {"bh": lab.bh, "core": core, "core_bh": lab.bh + core / 6, "bh_short": lab.bh + hedge}.items()}
    yrs = lab.years
    yearly = {k: {int(y): round(float(v), 0) for y, v in pd.Series(b[m]).groupby(yrs[m]).sum().items()}
              for k, b in books.items()}
    p = g[g.setup.str.startswith(("P_", "S_"))]
    fams = p.groupby(["family", "side"]).agg(n=("total", "size"), pos=("_pos", "mean"), passed=("pass_basic", "sum"),
                                             med_pf=("pf", "median")).reset_index()
    out = dict(dates=[str(x.date()) for x in idx[wk]], curves=curves, pct=pct, yearly=yearly,
               funnel=json.load(open(RES / "protocol_funnel.json")),
               confirm_singles=pd.read_csv(RES / "confirm_2008_singles.csv").to_dict("records"),
               confirm_books=pd.read_csv(RES / "confirm_2008_books.csv").to_dict("records"),
               protocol_families=fams.sort_values("pos", ascending=False).to_dict("records"),
               wf=pd.read_csv(RES / "protocol_wf.csv").to_dict("records"))
    json.dump(out, open(RES / "report_v2_data.json", "w"), default=float)
    print(json.dumps(pct, indent=0)[:1500])


if __name__ == "__main__":
    main()
