"""Evaluation protocol shared by every hypothesis.

A hypothesis is a boolean condition on 5-minute bars or on days. Its direction is NOT given:
it is set from the sign of the discovery-period result, so each condition is one test.

  forward return    bps from the signal close to the horizon (30 min, 2 h, RTH close, next RTH close,
                    or for days: close->close, open->close, close->open, 5 and 20 days)
  null              mean forward return of the same 30-min time-of-day bucket (bars) or of all days
                    (days) in the same calendar year, so long bias and changing drift are removed
  excess            direction * (forward - null)
  non-overlap       events closer than the horizon to the previous kept event are dropped
  periods           DISC 2008-16 selects direction and significance, VAL 2017-21 and TEST 2022-26
                    must confirm it with the same direction
  multiple testing  Benjamini-Hochberg false discovery rate over all hypotheses in DISC
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from numba import njit

COST_PTS = 0.5
HORIZONS_BAR = {"30m": 6, "2h": 24, "eod": -1, "next": -2}
HORIZONS_DAY = ["cc", "oc", "on", "c5", "c20"]
PER = ["DISC", "VAL", "TEST"]


@njit(cache=True)
def thin(idx, span):
    """keep events at least `span` apart (idx sorted)."""
    out = np.empty(len(idx), np.int64)
    m = 0
    last = -10 ** 12
    for i in idx:
        if i >= last + span:
            out[m] = i
            m += 1
            last = i
    return out[:m]


class Factory:
    def __init__(self, D):
        self.D = D
        T = D.T
        n = len(D.o)
        c = D.c
        di = D.di
        dayok = np.zeros(len(D.days), bool)
        dayok[D.dpos[T.index].to_numpy()] = True
        # map each bar to the RTH close index of its own day and of the next trading day
        close_i = np.full(len(D.days), -1)
        close_i[D.dpos[T.index].to_numpy()] = T.i_close.to_numpy().astype(int)
        nxt_close = np.full(len(D.days), -1)
        tpos = D.dpos[T.index].to_numpy()
        nxt_close[tpos[:-1]] = T.i_close.to_numpy().astype(int)[1:]
        self.fwd = {}
        for k, h in HORIZONS_BAR.items():
            f = np.full(n, np.nan)
            if h > 0:
                j = np.arange(n) + h
                ok = j < n
                jj = np.where(ok, j, 0)
                same = ok & (di[jj] == di)
                f[same] = (c[jj[same]] / c[same] - 1) * 1e4
            elif h == -1:
                ci = close_i[di]
                ok = (ci > np.arange(n))
                f[ok] = (c[ci[ok]] / c[ok] - 1) * 1e4
            else:
                ci = nxt_close[di]
                ok = ci > 0
                f[ok] = (c[ci[ok]] / c[ok] - 1) * 1e4
            self.fwd[k] = f
        # null: mean by (year, 30-min bucket)
        yr = pd.DatetimeIndex(D.gday).year.to_numpy()
        self.bucket = (yr - 2000) * 100 + D.gmin // 30
        self.null = {}
        for k, f in self.fwd.items():
            s = pd.Series(f).groupby(self.bucket).transform("mean").to_numpy()
            self.null[k] = s
        self.cost_bar = COST_PTS / c * 1e4
        self.span_bar = {"30m": 6, "2h": 24, "eod": 400, "next": 400}
        self.bar_period = D.period
        self.bar_day = di
        # daily forward returns (bps)
        C, O, pC = T.C.to_numpy(), T.O.to_numpy(), T.pC.to_numpy()
        self.dfwd = {"cc": (C / pC - 1) * 1e4, "oc": (C / O - 1) * 1e4, "on": (O / pC - 1) * 1e4,
                     "c5": (np.r_[C[5:], [np.nan] * 5] / C - 1) * 1e4,
                     "c20": (np.r_[C[20:], [np.nan] * 20] / C - 1) * 1e4}
        # cc/oc/on are returns OF day d (condition must be known before); c5/c20 start at close of d
        dy = T.index.year.to_numpy()
        self.dnull = {k: pd.Series(v).groupby(dy).transform("mean").to_numpy() for k, v in self.dfwd.items()}
        self.dcost = COST_PTS / C * 1e4
        self.dspan = {"cc": 1, "oc": 1, "on": 1, "c5": 5, "c20": 20}
        self.day_period = T.period.to_numpy()
        self.results = []

    # --------------------------------------------------------------- evaluation
    def _stats(self, ex, net, per):
        out = {}
        for p in PER:
            m = per == p
            x, y = ex[m], net[m]
            nn = int(m.sum())
            if nn >= 2:
                sd = x.std(ddof=1)
                out[p] = (nn, x.mean(), x.mean() / sd * math.sqrt(nn) if sd > 0 else 0.0, y.mean(), (y > 0).mean())
            else:
                out[p] = (nn, np.nan, np.nan, np.nan, np.nan)
        return out

    def bar(self, name, family, mask, horizons=("30m", "2h", "eod"), **meta):
        idx_all = np.flatnonzero(mask)
        for hk in horizons:
            f = self.fwd[hk]
            idx = idx_all[np.isfinite(f[idx_all])]
            if len(idx) < 20:
                continue
            idx = thin(idx.astype(np.int64), self.span_bar[hk]) if hk in ("30m", "2h") else _one_per_day(idx, self.bar_day)
            raw = f[idx] - self.null[hk][idx]
            per = self.bar_period[idx]
            self._record(name, family, "bar", hk, raw, f[idx], self.cost_bar[idx], per, meta)

    def day(self, name, family, mask, horizons=("cc", "oc", "c5"), known="close", **meta):
        """known='close': condition is known at the RTH close of day d -> same-day horizons
        (cc/oc/on) are applied to day d+1, c5/c20 start at the close of d.
        known='before': condition is known before day d starts (calendar) -> cc/oc/on of day d."""
        mask = np.asarray(mask, bool)
        shifted = np.r_[False, mask[:-1]]
        for hk in horizons:
            use = shifted if (known == "close" and hk in ("cc", "oc", "on")) else mask
            idx_all = np.flatnonzero(use)
            f = self.dfwd[hk]
            idx = idx_all[np.isfinite(f[idx_all])]
            if len(idx) < 20:
                continue
            idx = thin(idx.astype(np.int64), self.dspan[hk])
            raw = f[idx] - self.dnull[hk][idx]
            per = self.day_period[idx]
            self._record(name, family, "day", hk, raw, f[idx], self.dcost[idx], per, meta)

    def _record(self, name, family, level, hk, raw, fw, cost, per, meta):
        disc = per == "DISC"
        if disc.sum() < 30:
            return
        sgn = 1.0 if raw[disc].mean() >= 0 else -1.0
        ex = sgn * raw
        net = sgn * fw - cost
        st = self._stats(ex, net, per)
        r = dict(name=name, family=family, level=level, horizon=hk, dir="long" if sgn > 0 else "short", **meta)
        for p in PER:
            n_, m_, t_, nt_, w_ = st[p]
            r[f"n_{p}"], r[f"ex_{p}"], r[f"t_{p}"], r[f"net_{p}"], r[f"win_{p}"] = n_, m_, t_, nt_, w_
        self.results.append(r)

    def table(self, q=0.10):
        R = pd.DataFrame(self.results)
        t = R.t_DISC.abs().to_numpy()
        p = np.array([math.erfc(x / math.sqrt(2)) for x in t])
        R["p_DISC"] = p
        order = np.argsort(p)
        m = len(p)
        thr = q * (np.arange(1, m + 1)) / m
        passed = p[order] <= thr
        kmax = np.max(np.where(passed)[0]) if passed.any() else -1
        R["fdr"] = False
        if kmax >= 0:
            R.loc[R.index[order[:kmax + 1]], "fdr"] = True
        R["confirm"] = R.fdr & (R.ex_VAL > 0) & (R.ex_TEST > 0)
        R["tradeable"] = R.confirm & (R.net_DISC > 0) & (R.net_VAL > 0) & (R.net_TEST > 0)
        R["ex_LATER"] = (R.ex_VAL * R.n_VAL + R.ex_TEST * R.n_TEST) / (R.n_VAL + R.n_TEST)
        return R


def _one_per_day(idx, day):
    _, first = np.unique(day[idx], return_index=True)
    return idx[first]
