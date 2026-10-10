"""Exit variants and pause rules for selected high-RRR configurations.

Exit variants (stop in points, target R x stop):
  FIX          fixed stop and target
  BE b         stop to entry once the trade is b R in profit
  TRAIL a@b    once b R in profit, stop trails a R behind the best price (target kept)
  RUN a@b      as TRAIL but without a target (let the winner run until the trail or horizon)
Inside a bar the existing stop is checked first, then the best price is updated (conservative).

Pause rules on the single-position sequence:
  after k losses stop trading until a shadow trade wins (k = 3, 5, 8)
  after k losses skip the next N eligible trades
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import load_1m, COST  # noqa: E402

SCAN = "/tmp/claude-0/data/hr_scan.pkl"


@njit(cache=True)
def sim_exit(o, h, l, c, i0, end, side, sl, rr, be_at, tr_after, tr_dist, use_tp):
    """returns pnl in R (gross), exit index, code (1 tp, -1 stop at loss, 2 stop at >= 0, 0 time)."""
    ep = o[i0]
    stop = -sl          # stop as favourable distance from entry (negative = loss side)
    best = 0.0
    for k in range(i0, end):
        if side > 0:
            adv_px = l[k] - ep
            fav_px = h[k] - ep
        else:
            adv_px = ep - h[k]
            fav_px = ep - l[k]
        if adv_px <= stop:
            r = stop / sl
            return r, k, (-1 if r < 0 else 2)
        if use_tp and fav_px >= rr * sl:
            return rr, k, 1
        if fav_px > best:
            best = fav_px
            if be_at > 0 and best >= be_at * sl and stop < 0:
                stop = 0.0
            if tr_after > 0 and best >= tr_after * sl:
                ns = best - tr_dist * sl
                if ns > stop:
                    stop = ns
    r = side * (c[end - 1] - ep) / sl
    return r, end - 1, 0


@njit(cache=True)
def sim_many(o, h, l, c, i0s, ends, sides, sl, rr, be_at, tr_after, tr_dist, use_tp):
    n = len(i0s)
    pnl = np.zeros(n); ex = np.zeros(n, np.int64); code = np.zeros(n, np.int8)
    for e in range(n):
        p, k, cd = sim_exit(o, h, l, c, i0s[e], ends[e], sides[e], sl, rr, be_at, tr_after, tr_dist, use_tp)
        pnl[e] = p; ex[e] = k; code[e] = cd
    return pnl, ex, code


@njit(cache=True)
def seq(entry, ex, take):
    out = np.empty(len(entry), np.int64); m = 0; busy = -1
    for e in range(len(entry)):
        if take[e] and entry[e] > busy:
            out[m] = e; m += 1; busy = ex[e]
    return out[:m]


def streak_info(x):
    longest = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        longest = max(longest, cur)
    return longest


EXITS = [("FIX", 0, 0, 0, True), ("BE 1R", 1, 0, 0, True), ("BE 2R", 2, 0, 0, True), ("BE 3R", 3, 0, 0, True),
         ("TRAIL 1R@2R", 0, 2, 1, True), ("TRAIL 2R@3R", 0, 3, 2, True), ("TRAIL 3R@5R", 0, 5, 3, True),
         ("RUN 2R@3R", 0, 3, 2, False), ("RUN 3R@5R", 0, 5, 3, False), ("RUN 5R@8R", 0, 8, 5, False)]


def exit_study(configs, ends_key="5D"):
    """configs: list of dicts with entry mask (bool over E), sl, rr, label."""
    S = pickle.load(open(SCAN, "rb"))
    E = S["E"]
    X = load_1m()
    from context import horizon_ends
    eod, end5, _ = horizon_ends(X, E)
    rows = []
    per = E.period.to_numpy()
    for cf in configs:
        m = cf["mask"]
        idx = np.flatnonzero(m)
        ends = (end5 if cf["hz"] == "5D" else eod)[idx]
        for nm, be, tra, trd, use_tp in EXITS:
            pnl, ex, code = sim_many(X.o, X.h, X.l, X.c, E.i1.to_numpy()[idx].astype(np.int64), ends.astype(np.int64),
                                     E.side.to_numpy()[idx].astype(np.int64), float(cf["sl"]), float(cf["rr"]),
                                     float(be), float(tra), float(trd), use_tp)
            net = pnl - COST / cf["sl"]
            take = seq(E.i1.to_numpy()[idx].astype(np.int64), ex, np.ones(len(idx), bool))
            x = net[take]; cd = code[take]; pp = per[idx][take]
            r = dict(config=cf["label"], exit=nm, n=len(x), exp=x.mean(), tp=(cd == 1).mean(),
                     stop_loss=(cd == -1).mean(), stop_flat=(cd == 2).mean(), timeout=(cd == 0).mean(),
                     win=(x > 0).mean(), longest=streak_info(x), sumR=x.sum())
            for p in ("DISC", "VAL", "TEST"):
                r[f"exp_{p}"] = x[pp == p].mean() if (pp == p).any() else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


def pause_rules(x):
    """x: chronological net R of the eligible trades. Returns dict rule -> stats on taken trades."""
    out = {"bez pauzy": x}
    for k in (3, 5, 8):
        taken = []
        streak = 0
        paused = False
        for v in x:
            if not paused:
                taken.append(v)
                streak = streak + 1 if v < 0 else 0
                if streak >= k:
                    paused = True
            else:
                if v > 0:          # shadow win ends the pause, this trade itself was skipped
                    paused = False
                    streak = 0
        out[f"po {k} ztrátách pauza do stínové výhry"] = np.array(taken)
        for N in (5, 20):
            taken = []
            streak = 0
            skip = 0
            for v in x:
                if skip > 0:
                    skip -= 1
                    continue
                taken.append(v)
                streak = streak + 1 if v < 0 else 0
                if streak >= k:
                    skip = N
                    streak = 0
            out[f"po {k} ztrátách vynechat {N} obchodů"] = np.array(taken)
    rows = []
    for nm, t in out.items():
        rows.append(dict(rule=nm, n=len(t), exp=t.mean() if len(t) else np.nan, sumR=t.sum(), longest=streak_info(t)))
    return pd.DataFrame(rows)
