"""First-passage trades from event bars: entry at a given price on the event bar close, TP/SL price levels,
until the last bar of the Globex day (or a bar limit). Same-bar TP and SL counts as a loss. Cost per trade 0.5 pt."""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

COST = 0.5


@njit(cache=True)
def passage(H, L, C, idx, side, tp, sl, end):
    n = len(idx); res = np.zeros(n); out = np.zeros(n, np.int8)
    for k in range(n):
        i = idx[k]; e = C[i]; s = side[k]
        done = False
        for j in range(i + 1, end[k] + 1):
            hit_tp = (H[j] >= tp[k]) if s == 1 else (L[j] <= tp[k])
            hit_sl = (L[j] <= sl[k]) if s == 1 else (H[j] >= sl[k])
            if hit_sl:
                res[k] = (sl[k] - e) * s; out[k] = -1; done = True; break
            if hit_tp:
                res[k] = (tp[k] - e) * s; out[k] = 1; done = True; break
        if not done:
            res[k] = (C[end[k]] - e) * s
    return res, out


def summarize(name, f, idx, side, tp, sl, end, extra=None):
    """win rate vs the random-walk value SL/(TP+SL), points per trade after cost, t by day"""
    H = f.H.to_numpy(); L = f.L.to_numpy(); C = f.C.to_numpy()
    idx = np.asarray(idx); side = np.asarray(side, np.int64)
    if len(idx) < 30:
        return None
    res, out = passage(H, L, C, idx, side, tp, sl, end)
    e = C[idx]
    a = np.abs(tp - e); b = np.abs(e - sl)
    net = res - COST
    day = f.gday.to_numpy()[idx]
    s = pd.Series(net).groupby(day).mean()
    disc = f.ts.to_numpy()[idx] < np.datetime64("2019-01-01")
    closed = out != 0
    r = dict(test=name, n=len(idx), win=(out == 1).mean(), nedobeh=(out == 0).mean(),
             win_uzavrene=(out[closed] == 1).mean() if closed.any() else np.nan,
             nahodna_win=np.mean(b / (a + b)), tp_body=a.mean(), sl_body=b.mean(),
             hrube_b=res.mean(), cisty_b=net.mean(), t=s.mean() / s.std() * np.sqrt(len(s)),
             cisty_2011_18=net[disc].mean(), cisty_2019_26=net[~disc].mean())
    if extra:
        r.update(extra)
    return r
