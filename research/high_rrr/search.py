"""Filter search: which contexts cut losing trades for high-RRR systems?

For every entry type x horizon x stop (points) x RRR the single-position trade sequence is
evaluated with no filter (baseline), with every single context filter and with every pair of
filters from different context variables. A filter is robust when, against the same entry
type's baseline, it improves the expectancy in all three periods, has t >= 3 in DISC 2008-16
and t >= 1 in VAL 2017-21 and TEST 2022-26.
An empirical null repeats the whole search with context labels shuffled within each entry type
(same filter sizes, no information) to count how many 'robust' filters luck alone produces.
"""
from __future__ import annotations

import itertools
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd
from numba import njit, prange

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import SLS, RRS, COST  # noqa: E402

SCAN = "/tmp/claude-0/data/hr_scan.pkl"
OUT = os.path.join(HERE, "out")
VARS = ["regime", "dd", "rsiD", "rsiW", "rsiM", "rsi2", "bal", "flatD", "flatW", "flatM", "locD", "locW", "locM", "va5", "tod", "tests"]
NCOL = 13  # n, wins, sum, sumsq, losses, tp, longest, nstreaks, streak_total, ll, lprev, ge5, ge10


@njit(cache=True, parallel=True)
def eval_many(entry_i, exit_i, x, tp, per, masks):
    nm = masks.shape[0]
    out = np.zeros((nm, 4, NCOL))
    for m in prange(nm):
        busy = -1
        cur = 0
        prev_loss = False
        prev_p = -1
        for e in range(len(entry_i)):
            if not masks[m, e] or entry_i[e] <= busy:
                continue
            busy = exit_i[e]
            p = per[e]
            v = x[e]
            loss = v < 0
            for row in (p, 3):
                out[m, row, 0] += 1
                out[m, row, 2] += v
                out[m, row, 3] += v * v
                if v > 0:
                    out[m, row, 1] += 1
                if loss:
                    out[m, row, 4] += 1
                if tp[e]:
                    out[m, row, 5] += 1
                if prev_loss:
                    out[m, row, 10] += 1
                    if loss:
                        out[m, row, 9] += 1
            if loss:
                cur += 1
                if cur > out[m, 3, 6]:
                    out[m, 3, 6] = cur
                if cur > out[m, p, 6]:
                    out[m, p, 6] = cur
            else:
                if cur > 0:
                    for row in (prev_p, 3):
                        out[m, row, 7] += 1
                        out[m, row, 8] += cur
                        if cur >= 5:
                            out[m, row, 11] += 1
                        if cur >= 10:
                            out[m, row, 12] += 1
                cur = 0
            prev_loss = loss
            prev_p = p
        if cur > 0:
            for row in (prev_p, 3):
                if row >= 0:
                    out[m, row, 7] += 1
                    out[m, row, 8] += cur
                    if cur >= 5:
                        out[m, row, 11] += 1
                    if cur >= 10:
                        out[m, row, 12] += 1
    return out


def summarize(a):
    """a: (4, NCOL) -> dict of metrics per period (DISC, VAL, TEST, ALL)."""
    d = {}
    for i, p in enumerate(["DISC", "VAL", "TEST", "ALL"]):
        n = a[i, 0]
        if n < 2:
            d.update({f"n_{p}": n, f"exp_{p}": np.nan, f"t_{p}": np.nan})
            continue
        mu = a[i, 2] / n
        var = max(a[i, 3] / n - mu * mu, 1e-12) * n / (n - 1)
        d[f"n_{p}"] = int(n)
        d[f"exp_{p}"] = mu
        d[f"t_{p}"] = mu / np.sqrt(var / n)
        d[f"win_{p}"] = a[i, 1] / n
        d[f"tp_{p}"] = a[i, 5] / n
        d[f"loss_{p}"] = a[i, 4] / n
        d[f"longest_{p}"] = int(a[i, 6])
        d[f"mean_streak_{p}"] = a[i, 8] / a[i, 7] if a[i, 7] else 0
        d[f"ge10_per100_{p}"] = a[i, 12] / n * 100
        d[f"pll_{p}"] = a[i, 9] / a[i, 10] if a[i, 10] else np.nan
    return d


def subtypes(E):
    st = {}
    for (fam, sub, side), g in E.groupby(["fam", "sub", "side"]):
        st[f"{fam} · {sub} · {'long' if side > 0 else 'short'}"] = g.index.to_numpy()
    return st


def masks_for(Es, pairs=True, rng=None):
    """Es: entries of one subtype. Returns names, 2D bool masks. rng -> shuffled labels (null)."""
    cols = {}
    for v in VARS:
        if v == "tests":
            vals = np.where(Es.tests < 0, "na", np.minimum(Es.tests, 5).astype(str))
        else:
            vals = np.array([str(z) for z in Es[v].to_numpy()], dtype=object)
        if rng is not None:
            vals = rng.permutation(vals)
        cols[v] = vals
    singles = []
    for v, vals in cols.items():
        for u in np.unique(vals):
            if u in ("na", "nan", "None"):
                continue
            m = vals == u
            if m.sum() >= 60:
                singles.append((f"{v}={u}", v, m))
    names = ["(bez filtru)"] + [s[0] for s in singles]
    n_single = len(names)
    M = [np.ones(len(Es), bool)] + [s[2] for s in singles]
    if pairs:
        for (n1, v1, m1), (n2, v2, m2) in itertools.combinations(singles, 2):
            if v1 == v2:
                continue
            m = m1 & m2
            if m.sum() >= 60:
                names.append(f"{n1} & {n2}")
                M.append(m)
    return names, np.array(M), n_single


PAIR_SL = (10.0, 20.0, 30.0)
PAIR_RR = (3.0, 5.0, 10.0, 15.0)


def run(shuffle=False, sl_sel=None, rr_sel=None, pairs=True, seed=0):
    S = pickle.load(open(SCAN, "rb"))
    E, res = S["E"], S["res"]
    per = pd.Categorical(E.period, categories=["DISC", "VAL", "TEST"]).codes.astype(np.int64)
    rng = np.random.default_rng(seed) if shuffle else None
    rows = []
    for name, idx in subtypes(E).items():
        Es = E.loc[idx]
        names, M, n_single = masks_for(Es, pairs=pairs, rng=rng)
        ent = Es.i1.to_numpy().astype(np.int64)
        pr = per[idx]
        for hz in ("EOD", "5D"):
            code, exit_i, pnl = res[hz]
            for j, sl in enumerate(SLS):
                if sl_sel is not None and sl not in sl_sel:
                    continue
                for r, rr in enumerate(RRS):
                    if rr_sel is not None and rr not in rr_sel:
                        continue
                    x = pnl[idx, j, r].astype(np.float64) - COST / sl
                    ex = exit_i[idx, j, r].astype(np.int64)
                    tp = code[idx, j, r] == 1
                    use = len(names) if (sl in PAIR_SL and rr in PAIR_RR) else n_single
                    A = eval_many(ent, ex, x, tp, pr, M[:use])
                    base = summarize(A[0])
                    for k in range(use):
                        d = summarize(A[k])
                        if d.get("n_DISC", 0) < 30:
                            continue
                        row = dict(entry=name, hz=hz, sl=sl, rr=rr, filt=names[k], **d)
                        for p in ("DISC", "VAL", "TEST", "ALL"):
                            row[f"base_exp_{p}"] = base.get(f"exp_{p}")
                            row[f"base_win_{p}"] = base.get(f"win_{p}")
                            row[f"base_longest_{p}"] = base.get(f"longest_{p}")
                        rows.append(row)
        print(f"{name:40s} masks {len(names):5d}", flush=True)
    R = pd.DataFrame(rows)
    for c in R.columns:
        if R[c].dtype == np.float64:
            R[c] = R[c].astype(np.float32)
    return R


def robust(R):
    ok = ((R.t_DISC >= 3) & (R.t_VAL >= 1) & (R.t_TEST >= 1) & (R.n_VAL >= 15) & (R.n_TEST >= 15)
          & (R.exp_DISC > R.base_exp_DISC) & (R.exp_VAL > R.base_exp_VAL) & (R.exp_TEST > R.base_exp_TEST)
          & (R.filt != "(bez filtru)"))
    return R[ok]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    t = time.time()
    if mode == "real":
        R = run()
        R.to_parquet(os.path.join(OUT, "search_real.parquet"))
    else:
        R = run(shuffle=True, seed=int(mode[4:] or 0))
        R.to_parquet(os.path.join(OUT, f"search_{mode}.parquet"))
    rb = robust(R)
    print(mode, "evaluated", len(R), "robust", len(rb), "unique filters", rb.filt.nunique(), round(time.time() - t), "s")
