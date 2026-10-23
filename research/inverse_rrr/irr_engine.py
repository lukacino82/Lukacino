"""Inverse RRR engine: outcome of every TP x SL pair (in points) for every entry, TP may be smaller than SL.

For each entry (1-minute bar open) and side the scan records, for every TP level, the first bar where the
favourable excursion reaches it, and for every SL level the first bar where the adverse excursion reaches it.
A (TP, SL) trade wins if the TP bar comes strictly before the SL bar (same bar = loss, conservative); if neither
is hit before the horizon end the trade exits at that bar's close. Levels can be scaled per entry
(scale = 1 -> points; scale = ATR/50 -> "points at a daily ATR of 50").
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numba import njit, prange

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "high_rrr"))
from engine import load_1m  # noqa: E402  (cached 1-minute arrays o, h, l, c, gmin, gday)

TPS = np.array([4, 6, 8, 10, 12, 15, 20, 25], dtype=np.float64)
SLS = np.array([4, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 75, 100, 150], dtype=np.float64)
COST = 0.5


@njit(parallel=True, cache=True)
def first_hits(o, h, l, c, entries, ends, sides, scale, tps, sls, t_tp, t_sl, close_pnl):
    nE = len(entries)
    nT = len(tps); nS = len(sls)
    for e in prange(nE):
        i0 = entries[e]; end = ends[e]; s = sides[e]; ep = o[i0]; sc = scale[e]
        jt = 0; js = 0
        last = i0
        for k in range(i0, end):
            last = k
            if s > 0:
                fav = h[k] - ep; adv = ep - l[k]
            else:
                fav = ep - l[k]; adv = h[k] - ep
            while jt < nT and fav >= tps[jt] * sc:
                t_tp[e, jt] = k; jt += 1
            while js < nS and adv >= sls[js] * sc:
                t_sl[e, js] = k; js += 1
            if jt == nT and js == nS:
                break
        close_pnl[e] = s * (c[last] - ep)
        for j in range(jt, nT):
            t_tp[e, j] = 2**31 - 1
        for j in range(js, nS):
            t_sl[e, j] = 2**31 - 1


def run(X, entries, ends, sides, scale):
    nE = len(entries)
    t_tp = np.zeros((nE, len(TPS)), np.int32)
    t_sl = np.zeros((nE, len(SLS)), np.int32)
    cp = np.zeros(nE, np.float32)
    first_hits(X.o, X.h, X.l, X.c, entries.astype(np.int64), ends.astype(np.int64), sides.astype(np.int64),
               scale.astype(np.float64), TPS, SLS, t_tp, t_sl, cp)
    return t_tp, t_sl, cp


def pair_pnl(t_tp, t_sl, cp, it, js, scale):
    """net P&L in points for TP index it, SL index js (cost included)"""
    a = t_tp[:, it]; b = t_sl[:, js]
    win = a < b
    loss = (b <= a) & (b < 2**31 - 1)
    pnl = np.where(win, TPS[it] * scale, np.where(loss, -SLS[js] * scale, cp))
    code = np.where(win, 1, np.where(loss, -1, 0)).astype(np.int8)
    return pnl - COST, code
