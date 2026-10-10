"""Loss-streak analysis on top of the outcome scan."""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import SLS, RRS, COST, expected_longest  # noqa: E402

SCAN = "/tmp/claude-0/data/hr_scan.pkl"
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
PER = ["DISC", "VAL", "TEST"]


@njit(cache=True)
def eval_seq(entry_i, exit_i, x, mask, per, nper):
    """Single-position sequencing + per-period stats.
    returns array (nper+1, 11): n, wins, sum, losses, longest, nstreaks, streak_total, ll, lprev, ge5, ge10
    row nper = all periods together (streaks counted on the full sequence)."""
    out = np.zeros((nper + 1, 11))
    busy = -1
    cur = 0
    prev_loss = False
    prev_p = -1
    for e in range(len(entry_i)):
        if not mask[e] or entry_i[e] <= busy:
            continue
        busy = exit_i[e]
        p = per[e]
        v = x[e]
        for row in (p, nper):
            out[row, 0] += 1
            out[row, 2] += v
            if v > 0:
                out[row, 1] += 1
        loss = v < 0
        if loss:
            out[p, 3] += 1
            out[nper, 3] += 1
        # streak bookkeeping on the full sequence; attribute to the period where the streak ends
        if prev_loss:
            out[nper, 8] += 1
            out[p, 8] += 1
            if loss:
                out[nper, 7] += 1
                out[p, 7] += 1
        if loss:
            cur += 1
            if cur > out[nper, 4]:
                out[nper, 4] = cur
            if cur > out[p, 4]:
                out[p, 4] = cur
        else:
            if cur > 0:
                for row in (prev_p, nper):
                    if row >= 0:
                        out[row, 5] += 1
                        out[row, 6] += cur
                        if cur >= 5:
                            out[row, 9] += 1
                        if cur >= 10:
                            out[row, 10] += 1
            cur = 0
        prev_loss = loss
        prev_p = p
    if cur > 0:
        for row in (prev_p, nper):
            if row >= 0:
                out[row, 5] += 1
                out[row, 6] += cur
                if cur >= 5:
                    out[row, 9] += 1
                if cur >= 10:
                    out[row, 10] += 1
    return out


def stats_row(a, n_all=None):
    n = a[0]
    if n == 0:
        return dict(n=0)
    p_loss = a[3] / n
    d = dict(n=int(n), win=a[1] / n, exp=a[2] / n, loss=p_loss, longest=int(a[4]),
             mean_streak=a[6] / a[5] if a[5] else 0.0, ge5_per100=a[9] / n * 100, ge10_per100=a[10] / n * 100,
             p_ll=a[7] / a[8] if a[8] else np.nan)
    d["cluster"] = d["p_ll"] / p_loss if p_loss > 0 else np.nan
    d["exp_longest_iid"] = expected_longest(n, p_loss)
    return d


class Book:
    def __init__(self):
        S = pickle.load(open(SCAN, "rb"))
        self.E = S["E"]
        self.res = S["res"]
        self.per = pd.Categorical(self.E.period, categories=PER).codes.astype(np.int64)
        self.entry = self.E.i1.to_numpy().astype(np.int64)

    def arrays(self, hz, j, r):
        code, exit_i, pnl = self.res[hz]
        x = pnl[:, j, r].astype(np.float64) - COST / SLS[j]
        return exit_i[:, j, r].astype(np.int64), x

    def evaluate(self, hz, j, r, mask):
        ex, x = self.arrays(hz, j, r)
        a = eval_seq(self.entry, ex, x, mask, self.per, 3)
        out = {"ALL": stats_row(a[3])}
        for i, p in enumerate(PER):
            out[p] = stats_row(a[i])
        return out


def flat(name, hz, sl, rr, st, **meta):
    d = dict(name=name, hz=hz, sl=sl, rr=rr, **meta)
    for k, v in st.items():
        for kk, vv in v.items():
            d[f"{kk}_{k}"] = vv
    return d


def baseline(B: Book):
    E = B.E
    rows = []
    for fam_sub, m in (("GRID long", (E.fam == "GRID") & (E.side == 1)), ("GRID short", (E.fam == "GRID") & (E.side == -1))):
        m = m.to_numpy()
        for hz in ("EOD", "5D"):
            for j, sl in enumerate(SLS):
                for r, rr in enumerate(RRS):
                    rows.append(flat(fam_sub, hz, sl, rr, B.evaluate(hz, j, r, m)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    B = Book()
    R = baseline(B)
    R.to_csv(os.path.join(OUT, "baseline_grid.csv"), index=False)
    pd.set_option("display.width", 250)
    c = ["name", "hz", "sl", "rr", "n_ALL", "win_ALL", "exp_ALL", "longest_ALL", "exp_longest_iid_ALL", "mean_streak_ALL",
         "ge10_per100_ALL", "cluster_ALL", "exp_DISC", "exp_VAL", "exp_TEST"]
    print(R[(R.sl.isin([10, 20, 40])) & (R.rr.isin([1, 3, 5, 10, 20]))][c].round(3).to_string())
