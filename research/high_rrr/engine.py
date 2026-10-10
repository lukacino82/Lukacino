"""Outcome engine for high reward:risk research on ES2008 (1-minute, back-adjusted, ET).

One forward scan per entry gives the result for EVERY stop (points) x RRR pair at once:
  * first bar where the low reaches entry - SL       -> stop time of that SL
  * first bar where the high reaches entry + R x SL  -> target time of that level
  * win if the target bar comes strictly before the stop bar (same bar = loss, conservative)
  * if neither happens before the horizon end: exit at the close, P&L in R
Shorts are the mirror image. Entry is the open of the 1-minute bar after the signal.
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd
from numba import njit

SRC = "/tmp/claude-0/data/es2008.parquet"
CACHE = "/tmp/claude-0/data/hr_1m.pkl"
SLS = np.array([5, 8, 10, 12, 15, 20, 25, 30, 40, 50], dtype=np.float64)
RRS = np.array([1, 2, 3, 5, 8, 10, 12, 15, 20], dtype=np.float64)
COST = 0.5  # points per round trip


class M1:
    pass


def load_1m():
    """1-minute arrays filtered exactly like edge_factory.data.build, plus the 1-minute start
    index of every 5-minute bar (so 5-minute signals map to 1-minute entries)."""
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, "rb"))
    df = pd.read_parquet(SRC)
    ts = df.ts
    d = ts.dt.normalize()
    g = d.where(ts.dt.hour < 18, d + pd.Timedelta(days=1))
    wd = g.dt.dayofweek
    g = g.where(wd != 5, g + pd.Timedelta(days=2)).where(wd != 6, g + pd.Timedelta(days=1))
    gm = ((ts - (g - pd.Timedelta(hours=6))).dt.total_seconds() // 60).astype(int)
    keep = (gm >= 0) & (gm < 23 * 60)
    df, g, gm = df[keep], g[keep], gm[keep]
    gnum = ((g - pd.Timestamp("2000-01-01")).dt.days).to_numpy()
    k5 = gnum * 1000 + (gm.to_numpy() // 5)
    brk = np.r_[0, np.where(np.diff(k5) != 0)[0] + 1]
    X = M1()
    X.o = df.Open.to_numpy(float); X.h = df.High.to_numpy(float)
    X.l = df.Low.to_numpy(float); X.c = df.Close.to_numpy(float)
    X.gmin = gm.to_numpy()
    X.gday = g.to_numpy()
    X.b5 = brk                      # 1-minute index where each 5-minute bar starts
    pickle.dump(X, open(CACHE, "wb"), protocol=4)
    return X


@njit(cache=True)
def scan(o, h, l, c, entries, ends, sides, sls, rrs, code, exit_i, pnl):
    """code/exit_i/pnl: (nE, nS, nR) outputs."""
    nS, nR = len(sls), len(rrs)
    # all target levels as multiples of points
    for e in range(len(entries)):
        i0 = entries[e]
        end = ends[e]
        s = sides[e]
        ep = o[i0]
        t_stop = np.full(nS, -1, np.int64)
        t_tp = np.full((nS, nR), -1, np.int64)
        n_stopped = 0
        runmax = -1e18
        last = i0
        for k in range(i0, end):
            last = k
            if s > 0:
                adv = ep - l[k]
                fav = h[k] - ep
            else:
                adv = h[k] - ep
                fav = ep - l[k]
            # stops hit in this bar (conservative: the bar's favourable extreme does not count)
            for j in range(nS):
                if t_stop[j] < 0 and adv >= sls[j]:
                    t_stop[j] = k
                    n_stopped += 1
            if fav > runmax:
                runmax = fav
                for j in range(nS):
                    if t_stop[j] >= 0 and t_stop[j] < k:
                        continue
                    for r in range(nR):
                        if t_tp[j, r] < 0 and runmax >= rrs[r] * sls[j]:
                            t_tp[j, r] = k
            if n_stopped == nS:
                break
        for j in range(nS):
            for r in range(nR):
                tp = t_tp[j, r]
                st = t_stop[j]
                if tp >= 0 and (st < 0 or tp < st):
                    code[e, j, r] = 1
                    exit_i[e, j, r] = tp
                    pnl[e, j, r] = rrs[r]
                elif st >= 0:
                    code[e, j, r] = -1
                    exit_i[e, j, r] = st
                    pnl[e, j, r] = -1.0
                else:
                    code[e, j, r] = 0
                    exit_i[e, j, r] = last
                    pnl[e, j, r] = s * (c[last] - ep) / sls[j]
    return code, exit_i, pnl


def run_scan(X, entries, ends, sides):
    nE = len(entries)
    code = np.zeros((nE, len(SLS), len(RRS)), np.int8)
    exit_i = np.zeros((nE, len(SLS), len(RRS)), np.int64)
    pnl = np.zeros((nE, len(SLS), len(RRS)), np.float32)
    scan(X.o, X.h, X.l, X.c, entries.astype(np.int64), ends.astype(np.int64), sides.astype(np.int64),
         SLS, RRS, code, exit_i, pnl)
    return code, exit_i.astype(np.int32), pnl


# ------------------------------------------------------------------ sequencing
@njit(cache=True)
def sequence(entry_i, exit_i, take, pnl, cost_r):
    """Single-position system: take an eligible entry only when flat. Returns indices taken."""
    out = np.empty(len(entry_i), np.int64)
    m = 0
    busy = -1
    for e in range(len(entry_i)):
        if not take[e] or entry_i[e] <= busy:
            continue
        out[m] = e
        m += 1
        busy = exit_i[e]
    return out[:m]


@njit(cache=True)
def streak_stats(x):
    """x: P&L in R of a trade sequence. Losses = x < 0."""
    n = len(x)
    longest = 0
    cur = 0
    nstreak = 0
    total = 0
    ge5 = 0
    ge10 = 0
    ge20 = 0
    ll = 0
    l_prev = 0
    for i in range(n):
        if x[i] < 0:
            cur += 1
            if i > 0 and x[i - 1] < 0:
                ll += 1
        else:
            if cur > 0:
                nstreak += 1
                total += cur
                if cur >= 5:
                    ge5 += 1
                if cur >= 10:
                    ge10 += 1
                if cur >= 20:
                    ge20 += 1
            cur = 0
        if cur > longest:
            longest = cur
        if i < n - 1 and x[i] < 0:
            l_prev += 1
    if cur > 0:
        nstreak += 1
        total += cur
        if cur >= 5:
            ge5 += 1
        if cur >= 10:
            ge10 += 1
        if cur >= 20:
            ge20 += 1
    p_ll = ll / l_prev if l_prev > 0 else np.nan
    mean_streak = total / nstreak if nstreak > 0 else 0.0
    return longest, mean_streak, ge5, ge10, ge20, p_ll


def expected_longest(n, p_loss):
    """Expected longest run of losses in n i.i.d. trades (Schilling approximation)."""
    if n <= 0 or p_loss <= 0 or p_loss >= 1:
        return np.nan
    q = 1 / p_loss
    return np.log(n * (1 - p_loss)) / np.log(q) - 1 + 0.5772 / np.log(q) + 0.5
