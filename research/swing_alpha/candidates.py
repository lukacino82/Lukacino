"""Candidate swing systems built from the family-level result of Experiments A/B.

Experiment A/B: SW01-SW04 continuation rules have negative edge versus drift in DISC (2009-2018), so the
DISC-only conclusion is to trade them the other way. The candidate is defined once, from DISC
evidence, as an ensemble: enter LONG on the day after any bearish 'extreme' (the short versions of
the SW rules whose fade had DISC edge > 0 at 10D), single position, several exit models. The same
construction mirrored (short after bullish extremes) is reported as the control.
VAL (2019-2022) and OOS (2023-2026) are untouched by the choice of rules.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from signals import table, build_signals  # noqa: E402
from event_study import period, START, OUT, tstat  # noqa: E402
from experiment_b import EXITS, sim_seq, stats, flags  # noqa: E402

PICK_EXIT = "E01 čas 10D"


def choose_rules(B, side, thr=1.0):
    """rules whose fade (trade = `side`) had positive DISC edge at the 10-day time exit and n_DISC >= 40"""
    f = B[(B.family == "FADE") & (B.side == side) & (B.exit == PICK_EXIT) & (B.n_DISC >= 40) & (B.tedge_DISC >= thr)]
    return sorted(f.signal.str.replace("fade · ", "", regex=False).unique())


def main():
    B = pd.read_csv(os.path.join(OUT, "experiment_b.csv"))
    T = table()
    S = build_signals(T)
    O, H, L, C, A = (T[k].to_numpy(float) for k in ("O", "H", "L", "C", "ATR"))
    NH = np.fmax(T.hP.to_numpy(float), T.hN.shift(-1).to_numpy(float))
    NL = np.fmin(T.lP.to_numpy(float), T.lN.shift(-1).to_numpy(float))
    F = flags(T)
    valid = (T.index >= START) & np.isfinite(A) & T.nO.notna().to_numpy()
    per = period(T.index); yrs = T.index.year.to_numpy()
    zero = np.zeros(len(T), np.bool_)
    out_rows, curves, chosen = [], {}, {}
    every = valid.copy()
    sets = []
    for trade_side, lab_side in ((1, "long"), (-1, "short")):
        for thr, tag in ((1.0, "ansámbl fade"), (2.0, "jádro fade")):
            rules = choose_rules(B, lab_side, thr)
            chosen[f"{tag} ({lab_side})"] = rules
            # the fade of a rule = the rule's own signal on the opposite side
            m = np.zeros(len(T), bool)
            for fam, nm, sd, mask in S:
                if sd == -trade_side and nm in rules and fam != "REF":
                    m |= mask
            sets.append((trade_side, lab_side, f"{tag} ({lab_side})", m & valid))
        sets.append((trade_side, lab_side, f"každý den ({lab_side})", every))
    for trade_side, lab_side, name, mm in sets:
        ts = np.flatnonzero(mm).astype(np.int64)
        for lab, kind, a, b, maxd in EXITS:
            fl = F[(b + 1.0, trade_side)] if kind == 2 else zero
            pnl, ex, code, tk = sim_seq(ts, trade_side, kind, a, b, maxd, O, H, L, C, NH, NL, A, fl)
            ii = ts[tk]; x = pnl[tk] - 1.0 / A[ii]
            r = dict(system=name, side=lab_side, exit=lab, signals=int(mm.sum()))
            r.update(stats(x))
            r["hold"] = (ex[tk] - ii).mean()
            r["exp_c2"] = (pnl[tk] - 2.0 / A[ii]).mean()
            r["pts"] = (x * A[ii]).mean()      # mean net points per contract
            r["exposure"] = (ex[tk] - ii).sum() / valid.sum()
            for P in ("DISC", "VAL", "OOS"):
                s = per[ii] == P
                r[f"n_{P}"] = int(s.sum()); r[f"exp_{P}"] = x[s].mean() if s.any() else np.nan; r[f"t_{P}"] = tstat(x[s])
            out_rows.append(r)
            curves[(name, lab)] = (T.index[ii], x, x * A[ii])
    R = pd.DataFrame(out_rows)
    base = R[R.system.str.startswith("každý")].set_index(["side", "exit"])
    for c in ("exp", "exp_DISC", "exp_VAL", "exp_OOS"):
        R[f"base_{c}"] = [base.loc[(s, e), c] for s, e in zip(R.side, R.exit)]
    R.to_csv(os.path.join(OUT, "candidates.csv"), index=False)
    # equity curves (points per 1 contract and ATR units) for the report
    eq = []
    for (name, lab), (d, x, p) in curves.items():
        if lab in ("E01 čas 5D", "E01 čas 10D", "E01 čas 20D", "E06 SL 2.0 ATR · RRR 3", "E06 SL 1.0 ATR · RRR 3", "E02 trailing 3.0 ATR"):
            for dd, xx, pp in zip(d, x, p):
                eq.append((name, lab, dd, xx, pp))
    pd.DataFrame(eq, columns=["system", "exit", "date", "atr", "pts"]).to_csv(os.path.join(OUT, "candidate_trades.csv"), index=False)
    pd.Series({k: " | ".join(v) for k, v in chosen.items()}).to_csv(os.path.join(OUT, "candidate_rules.csv"))
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    print(chosen)
    c = ["system", "exit", "n", "exp", "base_exp", "pts", "win", "pf", "longest", "maxdd", "t", "exp_DISC", "exp_VAL", "exp_OOS",
         "base_exp_DISC", "base_exp_VAL", "base_exp_OOS", "hold", "exposure"]
    print(R[c].round(3).to_string())


if __name__ == "__main__":
    main()
