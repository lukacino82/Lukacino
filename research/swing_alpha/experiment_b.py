"""SWING ALPHA Experiment B: tradeable multi-day holding with exit models E01-E08 (SW05).

Path model per trading day j (from the 1-minute data, see features.py):
  RTH open O_j (gap check) -> RTH range H_j/L_j -> RTH close C_j -> post + next overnight range
  (max(hP_j, hN_j+1), min(lP_j, lN_j+1)) -> next RTH open O_j+1 ...
Entry at the RTH open of day t+1. Inside a segment the stop is checked before the target (conservative);
a gap through the stop at the RTH open fills at the open. Trailing stops are updated only after a
segment ends. Exits that depend on a daily close (weekly VWAP, migration, regime) are decided at the
close and executed at the next RTH open. All results are in units of the entry-day ATR14.

Exit models:
  E01 fixed time (exit at the RTH close of day t+h)
  E02 ATR trailing stop (initial stop = trail distance), max 20 days
  E03 close back through the weekly VWAP + 2 ATR stop, max 20 days
  E04 opposite value migration (VA mid moves against) + 2 ATR stop, max 20 days
  E05 regime turns against (opposite / Transition) + 2 ATR stop, max 20 days
  E06 fixed SL / TP (SL in ATR x RRR), max 20 days
  E07 partial: half at +1R, rest trailed 1.5 ATR, SL 1.5 ATR, max 20 days
  E08 time + trailing
Positions never overlap within one (entry, exit) combination.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from signals import table, build_signals  # noqa: E402
from event_study import period, START, OUT, tstat, bh  # noqa: E402

MAXD = 20
# (label, kind, a, b, maxdays)   kind: 0 time, 1 trail, 2 close-flag, 3 sl/tp, 4 partial
EXITS = [(f"E01 čas {h}D", 0, 0.0, 0.0, h) for h in (1, 2, 3, 5, 10, 20)]
EXITS += [(f"E02 trailing {k} ATR", 1, k, 0.0, MAXD) for k in (1.0, 1.5, 2.0, 3.0)]
EXITS += [("E03 close přes týdenní VWAP", 2, 2.0, 0.0, MAXD), ("E04 opačná migrace", 2, 2.0, 1.0, MAXD),
          ("E05 změna režimu", 2, 2.0, 2.0, MAXD)]
EXITS += [(f"E06 SL {s} ATR · RRR {r}", 3, s, r, MAXD) for s in (0.5, 1.0, 1.5, 2.0) for r in (1, 2, 3, 5)]
EXITS += [("E07 ½ na 1R + trailing", 4, 1.5, 1.0, MAXD)]
EXITS += [("E08 trailing 2 ATR, max 10D", 1, 2.0, 0.0, 10), ("E08 trailing 1 ATR, max 5D", 1, 1.0, 0.0, 5)]


@njit(cache=True)
def sim_one(t, side, kind, a, b, maxd, O, H, L, C, NH, NL, A, flag):
    """returns (pnl in ATR, exit day index, exit code 1 tp / -1 stop / 0 time / 2 flag)"""
    n = len(O)
    j = t + 1
    if j >= n:
        return np.nan, -1, 0
    ep = O[j]; atr = A[t]
    if not (atr > 0) or not np.isfinite(ep):
        return np.nan, -1, 0
    stop = -1e18; tp = 1e18
    if kind == 1 or kind == 2 or kind == 4:
        stop = -a * atr
    elif kind == 3:
        stop = -a * atr; tp = a * b * atr
    if kind == 4:
        tp = a * b * atr         # partial target at +1R
    best = 0.0
    half_done = False
    banked = 0.0
    last = min(t + maxd, n - 1)
    for d in range(j, last + 1):
        # RTH open (gap); on the entry day the open is the entry
        if d > j:
            x = side * (O[d] - ep)
            if x <= stop:
                return (banked + (0.5 if half_done else 1.0) * x) / atr, d, -1
            if x >= tp and kind == 3:
                return x / atr, d, 1
            if kind == 4 and not half_done and x >= tp:
                half_done = True; banked = 0.5 * x
        # RTH range
        if side > 0:
            adv = L[d] - ep; fav = H[d] - ep
        else:
            adv = ep - H[d]; fav = ep - L[d]
        if adv <= stop:
            return (banked + (0.5 if half_done else 1.0) * stop) / atr, d, -1
        if kind == 3 and fav >= tp:
            return tp / atr, d, 1
        if kind == 4 and not half_done and fav >= tp:
            half_done = True; banked = 0.5 * tp
        if fav > best:
            best = fav
        if kind == 1 or (kind == 4 and half_done):
            dist = a * atr
            if best - dist > stop:
                stop = best - dist
        # RTH close: time exit / close-based exit flag
        cx = side * (C[d] - ep)
        if d == last or (kind == 0 and d - t >= maxd):
            return (banked + (0.5 if half_done else 1.0) * cx) / atr, d, 0
        if kind == 2 and flag[d]:
            # decided at the close, executed at the next RTH open after the overnight segment
            if d + 1 < n:
                if side > 0:
                    advn = NL[d] - ep
                else:
                    advn = ep - NH[d]
                if np.isfinite(advn) and advn <= stop:
                    return stop / atr, d + 1, -1
                return side * (O[d + 1] - ep) / atr, d + 1, 2
            return cx / atr, d, 2
        # post-close + overnight segment
        if side > 0:
            advn = NL[d] - ep; favn = NH[d] - ep
        else:
            advn = ep - NH[d]; favn = ep - NL[d]
        if np.isfinite(advn) and advn <= stop:
            return (banked + (0.5 if half_done else 1.0) * stop) / atr, d + 1, -1
        if np.isfinite(favn):
            if kind == 3 and favn >= tp:
                return tp / atr, d + 1, 1
            if kind == 4 and not half_done and favn >= tp:
                half_done = True; banked = 0.5 * tp
            if favn > best:
                best = favn
            if kind == 1 or (kind == 4 and half_done):
                dist = a * atr
                if best - dist > stop:
                    stop = best - dist
    return np.nan, -1, 0


@njit(cache=True)
def sim_seq(ts, side, kind, a, b, maxd, O, H, L, C, NH, NL, A, flag):
    """single position: next entry only after the previous exit day"""
    m = len(ts)
    pnl = np.full(m, np.nan); ex = np.full(m, -1); code = np.zeros(m, np.int8); taken = np.zeros(m, np.bool_)
    busy = -1
    for k in range(m):
        t = ts[k]
        if t + 1 <= busy:
            continue
        p, e, c = sim_one(t, side, kind, a, b, maxd, O, H, L, C, NH, NL, A, flag)
        if e < 0 or not np.isfinite(p):
            continue
        pnl[k] = p; ex[k] = e; code[k] = c; taken[k] = True
        busy = e
    return pnl, ex, code, taken


def stats(x):
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return dict(n=0)
    eq = np.cumsum(x)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    longest = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        longest = max(longest, cur)
    g = x[x > 0].sum(); l_ = -x[x < 0].sum()
    return dict(n=len(x), exp=x.mean(), sum=x.sum(), win=(x > 0).mean(), pf=g / l_ if l_ > 0 else np.nan,
                maxdd=dd, longest=longest, t=tstat(x))


def flags(T):
    """close-based exit flags per side: index 0 long, 1 short"""
    out = {}
    out[(1.0, 1)] = (T.C < T.vwapW).to_numpy(); out[(1.0, -1)] = (T.C > T.vwapW).to_numpy()
    out[(2.0, 1)] = (T.dVA < 0).to_numpy(); out[(2.0, -1)] = (T.dVA > 0).to_numpy()   # b=1 -> E04
    out[(3.0, 1)] = np.isin(T.regime, ["Bear", "Transition"]); out[(3.0, -1)] = np.isin(T.regime, ["Bull", "Transition"])
    return out


def main():
    T = table()
    S = build_signals(T)
    # fades: every non-reference rule traded in the opposite direction
    S += [("FADE", "fade · " + nm, -sd, m) for fam, nm, sd, m in S if fam not in ("REF",)]
    O, H, L, C, A = (T[k].to_numpy(float) for k in ("O", "H", "L", "C", "ATR"))
    NH = np.fmax(T.hP.to_numpy(float), T.hN.shift(-1).to_numpy(float))
    NL = np.fmin(T.lP.to_numpy(float), T.lN.shift(-1).to_numpy(float))
    F = flags(T)
    valid = (T.index >= START) & np.isfinite(A) & T.nO.notna().to_numpy()
    per = period(T.index)
    idx_dates = T.index
    zero = np.zeros(len(T), np.bool_)
    rows = []
    trades = {}
    for fam, nm, side, m in S:
        ts = np.flatnonzero(m & valid).astype(np.int64)
        if len(ts) < 20:
            continue
        for ei, (lab, kind, a, b, maxd) in enumerate(EXITS):
            fl = zero
            if kind == 2:
                fl = F[(b + 1.0, side)]
            pnl, ex, code, tk = sim_seq(ts, side, kind, a, b, maxd, O, H, L, C, NH, NL, A, fl)
            ii = ts[tk]; x = pnl[tk]; cd = code[tk]; exd = ex[tk]
            costpt = 1.0 / A[ii]          # 1 ES point round trip (slippage + commission), in ATR
            r = dict(family=fam, signal=nm, side="long" if side > 0 else "short", exit=lab)
            st = stats(x - costpt)
            r.update(st)
            r["exp_gross"] = x.mean()
            for cpt in (0.5, 2.0):
                r[f"exp_c{cpt}"] = (x - cpt / A[ii]).mean()
            r["hold"] = (exd - ii).mean()
            r["tp"] = (cd == 1).mean(); r["stop"] = (cd == -1).mean()
            for P in ("DISC", "VAL", "OOS"):
                s = per[ii] == P
                xs = (x - costpt)[s]
                r[f"n_{P}"] = int(s.sum()); r[f"exp_{P}"] = xs.mean() if s.any() else np.nan; r[f"t_{P}"] = tstat(xs)
            rows.append(r)
            trades[(fam, nm, side, lab)] = (ii, exd, x - costpt)
    B = pd.DataFrame(rows)
    # benchmark: the same exit with an entry every day (same side); edge = trade minus the benchmark's
    # mean of the same calendar year (removes drift and exposure-time effects)
    yrs = idx_dates.year.to_numpy()
    bmean = {}
    for (fam, nm, side, lab), (ii, exd, x) in trades.items():
        if nm == "každý den":
            bmean[(side, lab)] = pd.Series(x).groupby(yrs[ii]).mean()
    ed = []
    for (fam, nm, side, lab), (ii, exd, x) in trades.items():
        e = x - bmean[(side, lab)].reindex(yrs[ii]).to_numpy()
        trades[(fam, nm, side, lab)] = (ii, exd, x, e)
        r = dict(t_edge=tstat(e), edge=np.nanmean(e))
        for P in ("DISC", "VAL", "OOS"):
            s_ = per[ii] == P
            r[f"edge_{P}"] = np.nanmean(e[s_]) if s_.any() else np.nan
            r[f"tedge_{P}"] = tstat(e[s_])
        ed.append(r)
    B = pd.concat([B, pd.DataFrame(ed)], axis=1)
    base = B[B.signal == "každý den"].set_index(["side", "exit"])
    for c in ("exp", "exp_DISC", "exp_VAL", "exp_OOS"):
        B[f"base_{c}"] = [base.loc[(s, e), c] for s, e in zip(B.side, B.exit)]
    B["robust"] = ((B.edge_DISC > 0) & (B.edge_VAL > 0) & (B.edge_OOS > 0) & (B.exp_DISC > 0) & (B.exp_VAL > 0) & (B.exp_OOS > 0)
                   & (B.tedge_DISC >= 2) & (B.n_VAL >= 15) & (B.n_OOS >= 15))
    from scipy.stats import norm
    B["p"] = 2 * (1 - norm.cdf(B.t_edge.abs()))
    B["fdr"] = bh(B.p.to_numpy())
    B.to_csv(os.path.join(OUT, "experiment_b.csv"), index=False)

    # exit model comparison averaged over all entries (does the exit itself matter?)
    ex_tab = B.groupby(["side", "exit"]).agg(entries=("exp", "size"), exp=("exp", "mean"), edge=("edge", "mean"),
                                            win=("win", "mean"), longest=("longest", "median"), hold=("hold", "mean")).reset_index()
    ex_tab.to_csv(os.path.join(OUT, "exit_models.csv"), index=False)

    # walk-forward: each year pick the best (entry, exit) by its trailing 4-year t-stat (embargo 30 days)
    wf_rows = []; wf_trades = []
    keys = list(trades.keys())
    years = range(2013, int(T.index.year.max()) + 1)
    for side_set, label in (((1, -1), "long+short"), ((1,), "long")):
        kk = [k for k in keys if k[2] in side_set and k[1] != "každý den"]
        for Y in years:
            t0 = pd.Timestamp(Y - 4, 1, 1); t1 = pd.Timestamp(Y, 1, 1) - pd.Timedelta(days=30)
            best = None; bt = -9
            for k in kk:
                ii, exd, x, e = trades[k]
                s = (idx_dates[ii] >= t0) & (idx_dates[np.minimum(exd, len(T) - 1)] < t1)
                if s.sum() < 30:
                    continue
                tt = tstat(e[s])
                if np.isfinite(tt) and tt > bt:
                    bt = tt; best = k
            if best is None:
                continue
            ii, exd, x, e = trades[best]
            s = idx_dates[ii].year == Y
            wf_rows.append(dict(mode=label, year=Y, pick=f"{best[1]} · {'L' if best[2] > 0 else 'S'} · {best[3]}", t_train=bt,
                                n=int(s.sum()), exp=x[s].mean() if s.any() else np.nan, sum=x[s].sum()))
            wf_trades += [(label, Y, d, v) for d, v in zip(idx_dates[ii][s], x[s])]
    WF = pd.DataFrame(wf_rows); WF.to_csv(os.path.join(OUT, "walk_forward.csv"), index=False)
    WT = pd.DataFrame(wf_trades, columns=["mode", "year", "date", "pnl"]); WT.to_csv(os.path.join(OUT, "walk_forward_trades.csv"), index=False)

    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 46)
    c = ["family", "signal", "side", "exit", "n", "exp", "base_exp", "edge", "t_edge", "win", "pf", "longest", "maxdd", "edge_DISC", "edge_VAL", "edge_OOS", "fdr"]
    print("combos", len(B), "robust", B.robust.sum(), "fdr", B.fdr.sum())
    print(B[B.robust].sort_values("t_edge", ascending=False)[c].head(40).round(3).to_string())
    print(ex_tab.round(3).to_string())
    print(WF.round(3).to_string())
    for md in WT["mode"].unique():
        x = WT[WT["mode"] == md].pnl.to_numpy()
        print(md, stats(x))


if __name__ == "__main__":
    main()
