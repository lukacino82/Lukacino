"""Mega scan, daily layer: every pair of signals (i AND j) x regime x outcome.

Test = mean excess outcome (outcome minus the mean of all days of the same period) on days where both signals are true.
Periods: discovery 2008-2015, validation 2016-2020, holdout 2021-2026. A test counts if n >= 30 in discovery.
Candidates: |t| >= 4 in discovery (n >= 20 in the other periods) are stored with all three periods.
Null: the same scan with outcomes circularly shifted inside each period (signal-outcome link destroyed, the
autocorrelation of both kept) -> how many 'discoveries' and 'confirmations' arise by chance.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily as D

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
P_EDGES = [("D", "2008-01-01", "2016-01-01"), ("V", "2016-01-01", "2021-01-01"), ("H", "2021-01-01", "2030-01-01")]
TMIN = 4.0
TBINS = np.linspace(-10, 10, 81)


def stats(S, y):
    """S: T x N float32 (0/1), y: T (nan -> row dropped). returns n, mean, t (N x N)"""
    ok = np.isfinite(y)
    S = S[ok]; y = y[ok].astype(np.float32)
    n = S.T @ S
    sy = (S * y[:, None]).T @ S
    syy = (S * (y * y)[:, None]).T @ S
    with np.errstate(divide="ignore", invalid="ignore"):
        m = sy / n
        var = syy / n - m * m
        t = m / np.sqrt(np.maximum(var, 1e-12) / n)
    return n, m, t


def run(null=False, seed=0):
    o = D.build(); t = o["t"]; B = o["B"]; Y = o["Y"]; F = o["F"]
    idx = t.index
    per = {p: ((idx >= a) & (idx < b)) for p, a, b in P_EDGES}
    keep = (B[per["D"]].sum() >= 40) & (B[per["V"]].sum() >= 25) & (B[per["H"]].sum() >= 25)
    B = B.loc[:, keep]
    B = B.T.drop_duplicates().T
    names = np.array(B.columns); N = len(names)
    S = B.to_numpy().astype(np.float32)
    volr = F["atr14_100"].rolling(252, min_periods=200).rank(pct=True).to_numpy()
    ma200 = F["dma200"].to_numpy()
    regimes = {"vse": np.ones(len(idx), bool), "nad MA200": ma200 > 0, "pod MA200": ma200 < 0,
               "volatilita vysoka": volr > 0.5, "volatilita nizka": volr <= 0.5}
    iu = np.triu(np.ones((N, N), bool))
    rng = np.random.default_rng(seed)
    rows = []; summ = []
    hist = np.zeros(len(TBINS) - 1, np.int64); tests = 0
    t0 = time.time()
    for rname, rm in regimes.items():
        for oname in Y.columns:
            y = Y[oname].to_numpy().copy()
            res = {}
            for p in "DVH":
                m = per[p] & rm
                yp = y[m]
                yp = yp - np.nanmean(y[per[p]])                 # excess over the unconditional mean of the period
                if null:
                    yp = np.roll(yp, rng.integers(40, max(41, len(yp) - 40)))
                res[p] = stats(S[m], yp)
            nD, mD, tD = res["D"]
            valid = iu & (nD >= 30)
            tests += int(valid.sum())
            hist += np.histogram(np.clip(tD[valid], -9.99, 9.99), TBINS)[0]
            nV, mV, tV = res["V"]; nH, mH, tH = res["H"]
            sel = valid & (np.abs(tD) >= TMIN) & (nV >= 20) & (nH >= 20)
            ii, jj = np.nonzero(sel)
            sgn = np.sign(tD[ii, jj])
            conf = (tV[ii, jj] * sgn >= 2)
            conf2 = conf & (tH[ii, jj] * sgn >= 2)
            summ.append(dict(regime=rname, outcome=oname, tests=int(valid.sum()), kandidatu=len(ii), potvrzeno_V=int(conf.sum()),
                             potvrzeno_V_i_H=int(conf2.sum())))
            if len(ii):
                rows.append(pd.DataFrame({"regime": rname, "outcome": oname, "i": ii.astype(np.int32), "j": jj.astype(np.int32),
                                          "nD": nD[ii, jj], "mD": mD[ii, jj], "tD": tD[ii, jj], "nV": nV[ii, jj], "mV": mV[ii, jj],
                                          "tV": tV[ii, jj], "nH": nH[ii, jj], "mH": mH[ii, jj], "tH": tH[ii, jj]}))
        print(("NULL " if null else "") + rname, "tests so far", tests, round(time.time() - t0), "s", flush=True)
    tag = f"null{seed}" if null else "real"
    pd.DataFrame(summ).to_csv(os.path.join(OUT, f"daily_scan_summary_{tag}.csv"), index=False)
    pd.DataFrame({"t_lo": TBINS[:-1], "count": hist}).to_csv(os.path.join(OUT, f"daily_scan_thist_{tag}.csv"), index=False)
    R = pd.concat(rows, ignore_index=True)
    R.to_parquet(os.path.join(D.CACHE, f"daily_candidates{'_null%d' % seed if null else ''}.parquet"))
    if not null:
        pd.Series(names).to_csv(os.path.join(D.CACHE, "daily_signal_names.csv"), index=False)
    print(tag, "DONE tests", tests, "signals", N, flush=True)


if __name__ == "__main__":
    run(null=len(sys.argv) > 1 and sys.argv[1] == "null", seed=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
