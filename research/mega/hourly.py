"""Mega scan, hourly layer (2011-2026, bid/ask delta available): decision at the close of every clock hour (ET).

Signals: hourly features ranked against the same hour of the previous 250 days (9 bins each), intraday states and the
daily context known at that time (yesterday's daily signals). Scan: every pair of signals x hour of day x regime x outcome.
Outcomes (ATR of the day): next 1 / 2 / 4 hourly bars, to the RTH close, next 23 bars; TP/SL on 1-minute bars until the
end of the Globex day: SL 0.1/0.2/0.35/0.5 ATR x RRR 1/2/3, long and short, cost 0.5 point.
Periods: discovery 2011-2016, validation 2017-2021, holdout 2022-2026. Null = outcomes shifted in time.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily as D
from scan_daily import stats, TBINS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
SLS = np.array([0.1, 0.2, 0.35, 0.5]); RRRS = np.array([1.0, 2.0, 3.0])
P_EDGES = [("D", "2011-01-01", "2017-01-01"), ("V", "2017-01-01", "2022-01-01"), ("H", "2022-01-01", "2030-01-01")]
CTX = ["rsi2<=5", "rsi2<=10", "rsi2<=20", "rsi2>=80", "rsi2>=90", "rsi2>=95", "wtd<=10", "wtd>=90", "nad_MA200", "pod_MA200",
       "atr14_100<=20", "atr14_100>=80", "pokles_v_rade>=2", "pokles_v_rade>=3", "rust_v_rade>=2", "rust_v_rade>=3", "ret5<=10",
       "ret5>=90", "ibs<=20", "ibs>=80", "vz_w<=10", "vz_w>=90", "vz_m<=10", "vz_m>=90", "nove_max_20", "nove_min_20", "dd20<=10",
       "rng>=90", "rng<=10", "close_pod_vcerejsim_low", "close_nad_vcerejsim_high", "dl1<=10", "dl1>=90", "vr20>=90", "NR7", "WR7"]


def build():
    p = os.path.join(D.CACHE, "hourly.pkl")
    if os.path.exists(p):
        return pd.read_pickle(p)
    f = pd.read_parquet(os.path.join(D.DATA, "dv", "frame.parquet"))
    f = f[f["mod"] // 60 != 17].reset_index(drop=True)
    hk = f.ts.dt.floor("h")
    g = f.groupby(hk)
    h = g.agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"), V=("V", "sum"), dl=("delta", "sum"),
              cd=("cd_g", "last"), vd=("vwap_d", "last"), sdd=("sd_d", "last"), vw=("vwap_w", "last"), sdw=("sd_w", "last"),
              vm=("vwap_m", "last"), sdm=("sd_m", "last"), atr=("atr", "last"), gday=("gday", "last"), nb=("C", "size"))
    h["e"] = g.apply(lambda x: x.index[-1], include_groups=False)
    h = h[h.nb >= 30].copy()
    h["hod"] = h.index.hour
    A = h.atr
    F = {}
    for k in (1, 2, 4, 8, 23):
        F[f"r{k}h"] = (h.C - h.C.shift(k)) / A
    rng = (h.H - h.L).replace(0, np.nan)
    F["rng1h"] = rng / A; F["loc1h"] = (h.C - h.L) / rng
    F["dl1h"] = h.dl / h.V.replace(0, np.nan); F["dl4h"] = h.dl.rolling(4).sum() / h.V.rolling(4).sum()
    dv = h.V.groupby(h.gday).cumsum(); F["cd_den"] = h.cd / dv
    F["vz_d"] = (h.C - h.vd) / h.sdd.replace(0, np.nan); F["vz_w"] = (h.C - h.vw) / h.sdw.replace(0, np.nan); F["vz_m"] = (h.C - h.vm) / h.sdm.replace(0, np.nan)
    dH = h.H.groupby(h.gday).cummax(); dL = h.L.groupby(h.gday).cummin(); dO = h.O.groupby(h.gday).transform("first")
    F["pos_den"] = (h.C - dL) / (dH - dL).replace(0, np.nan); F["ret_den"] = (h.C - dO) / A; F["rng_den"] = (dH - dL) / A
    o = D.build(); t = o["t"]; B = o["B"]
    days = t.index
    # daily context: last completed RTH day at the decision time
    pos = np.searchsorted(days.to_numpy(), h.gday.to_numpy())                    # index of gday in daily table (or next)
    is_day = (pos < len(days)) & (days.to_numpy()[np.minimum(pos, len(days) - 1)] == h.gday.to_numpy())
    after_close = np.asarray(h.index.hour == 16)          # 18:00+ already belongs to the next Globex day
    ctx = np.where(is_day & after_close, pos, pos - 1)
    ok_ctx = ctx >= 0
    pC = t.C.to_numpy()[np.maximum(ctx, 0)]; pH = t.H.to_numpy()[np.maximum(ctx, 0)]; pL = t.L.to_numpy()[np.maximum(ctx, 0)]
    F["od_vc_close"] = (h.C - pC) / A; F["od_vc_high"] = (h.C - pH) / A; F["od_vc_low"] = (h.C - pL) / A
    volh = h.V.groupby(h.hod).transform(lambda x: x.rolling(20).mean().shift())
    F["objem_rel"] = h.V / volh
    up = (h.C > h.C.shift()); st = up.groupby((up != up.shift()).cumsum()).cumcount() + 1
    F["serie_hod"] = np.where(up, st, -st).astype(float)
    F = pd.DataFrame(F, index=h.index)
    R = F.groupby(h.hod).transform(lambda x: x.rolling(250, min_periods=150).rank(pct=True))
    cols = {}
    for c in F.columns:
        r = R[c].to_numpy()
        for nm, lo, hi in D.BINS:
            cols[f"{c}{nm}" if nm[0] in "<>" else f"{c}:{nm}"] = (r <= hi) if lo == 0 else ((r >= lo) if hi > 1 else ((r > lo) & (r < hi)))
    names = ["Po", "Ut", "St", "Ct", "Pa"]
    for k in range(5):
        cols[f"den={names[k]}"] = (h.gday.dt.day_of_week == k).to_numpy()
    cols["nad_VWAP_d"] = (h.C > h.vd).to_numpy(); cols["pod_VWAP_d"] = (h.C < h.vd).to_numpy()
    cols["nad_VWAP_w"] = (h.C > h.vw).to_numpy(); cols["pod_VWAP_w"] = (h.C < h.vw).to_numpy()
    cols["nad_VWAP_m"] = (h.C > h.vm).to_numpy(); cols["pod_VWAP_m"] = (h.C < h.vm).to_numpy()
    cols["nad_vc_high"] = (h.C.to_numpy() > pH); cols["pod_vc_low"] = (h.C.to_numpy() < pL); cols["uvnitr_vc_range"] = (h.C.to_numpy() <= pH) & (h.C.to_numpy() >= pL)
    cols["CD_den>0"] = (h.cd > 0).to_numpy(); cols["CD_den<0"] = (h.cd < 0).to_numpy()
    cols["nove_high_dne"] = (h.H >= dH).to_numpy(); cols["nove_low_dne"] = (h.L <= dL).to_numpy()
    for k in (2, 3, 4):
        cols[f"hodin_nahoru>={k}"] = (F.serie_hod >= k).to_numpy(); cols[f"hodin_dolu>={k}"] = (F.serie_hod <= -k).to_numpy()
    Bd = B[CTX].to_numpy()
    for q, c in enumerate(CTX):
        cols["D:" + c] = Bd[np.maximum(ctx, 0), q] & ok_ctx
    S = pd.DataFrame({k: np.asarray(v, bool) for k, v in cols.items()}, index=h.index)
    # outcomes
    n = len(h); Cc = h.C.to_numpy(); Aa = A.to_numpy(); e = h.e.to_numpy()
    Y = {}
    for k in (1, 2, 4, 23):
        Y[f"dalsi {k} hod. svice"] = (np.r_[Cc[k:], np.full(k, np.nan)] - Cc) / Aa
    rc = f[f.rth].groupby("gday").C.last()
    rth_close = h.gday.map(rc).to_numpy()
    Y["do RTH close"] = np.where(np.asarray(h.index.hour * 60 + h.index.minute < 900), (rth_close - Cc) / Aa, np.nan)
    lastbar = pd.Series(np.arange(len(f))).groupby(f.gday.to_numpy()).max()
    end = h.gday.map(lastbar).to_numpy().astype(np.int64)
    ok = (end > e + 5) & np.isfinite(Aa)
    tps = np.unique(np.round(np.outer(SLS, RRRS).ravel(), 4))
    tsl, ttp, fin = D.tpsl(f.H.to_numpy(), f.L.to_numpy(), f.C.to_numpy(), e[ok].astype(np.int64), end[ok], Aa[ok], SLS, tps)
    for side, sn in ((0, "long"), (1, "short")):
        for i, s in enumerate(SLS):
            for r in RRRS:
                j = int(np.searchsorted(tps, round(s * r, 4)))
                a = tsl[:, side, i]; b = ttp[:, side, j]
                win = b < a; loss = (a <= b) & (a < (1 << 30))
                y = np.where(win, s * r, np.where(loss, -s, fin * (1 if side == 0 else -1))) - D.COST / Aa[ok]
                full = np.full(n, np.nan); full[ok] = y
                Y[f"{sn} SL{s:g} RRR{r:g}"] = full
    Y = pd.DataFrame(Y, index=h.index)
    out = dict(h=h, S=S, Y=Y, F=F)
    pd.to_pickle(out, p)
    return out


def run(null=False, seed=0):
    o = build(); h = o["h"]; S0 = o["S"]; Y = o["Y"]
    gd = h.gday
    per = {p: ((gd >= a) & (gd < b)).to_numpy() for p, a, b in P_EDGES}
    keep = (S0[per["D"]].sum() >= 800) & (S0[per["V"]].sum() >= 500) & (S0[per["H"]].sum() >= 500)
    S0 = S0.loc[:, keep]; S0 = S0.T.drop_duplicates().T
    names = np.array(S0.columns); N = len(names); S = S0.to_numpy().astype(np.float32)
    regimes = {"vse": np.ones(len(h), bool), "nad MA200": S0["D:nad_MA200"].to_numpy(), "pod MA200": S0["D:pod_MA200"].to_numpy(),
               "vol. vysoka": S0["D:atr14_100>=80"].to_numpy(), "vol. nizka": S0["D:atr14_100<=20"].to_numpy()}
    iu = np.triu(np.ones((N, N), bool)); rng = np.random.default_rng(seed)
    hod = h.hod.to_numpy()
    rows = []; summ = []; tests = 0; t0 = time.time(); hist = np.zeros(len(TBINS) - 1, np.int64)
    for hh in sorted(np.unique(hod)):
        mh = hod == hh
        for rname, rm in regimes.items():
            for oname in Y.columns:
                y = Y[oname].to_numpy()
                res = {}
                skip = False
                for p in "DVH":
                    m = per[p] & mh & rm
                    base = y[per[p] & mh]
                    if np.isfinite(base).sum() < 100:
                        skip = True; break
                    yp = y[m] - np.nanmean(base)
                    if null:
                        yp = np.roll(yp, rng.integers(20, max(21, len(yp) - 20)))
                    res[p] = stats(S[m], yp)
                if skip:
                    continue
                nD, mD, tD = res["D"]; nV, mV, tV = res["V"]; nH, mH, tH = res["H"]
                valid = iu & (nD >= 40)
                tests += int(valid.sum())
                hist += np.histogram(np.clip(tD[valid], -9.99, 9.99), TBINS)[0]
                sel = valid & (np.abs(tD) >= 4.0) & (nV >= 25) & (nH >= 25)
                ii, jj = np.nonzero(sel)
                if len(ii):
                    rows.append(pd.DataFrame({"hod": hh, "regime": rname, "outcome": oname, "i": ii.astype(np.int32), "j": jj.astype(np.int32),
                                              "nD": nD[ii, jj], "mD": mD[ii, jj], "tD": tD[ii, jj], "nV": nV[ii, jj], "mV": mV[ii, jj],
                                              "tV": tV[ii, jj], "nH": nH[ii, jj], "mH": mH[ii, jj], "tH": tH[ii, jj]}))
        print(("NULL " if null else "") + f"hod {hh}", tests, round(time.time() - t0), "s", flush=True)
    tag = f"null{seed}" if null else "real"
    R = pd.concat(rows, ignore_index=True)
    R.to_parquet(os.path.join(D.CACHE, f"hourly_candidates_{tag}.parquet"))
    pd.DataFrame({"t_lo": TBINS[:-1], "count": hist}).to_csv(os.path.join(OUT, f"hourly_scan_thist_{tag}.csv"), index=False)
    if not null:
        pd.Series(names).to_csv(os.path.join(D.CACHE, "hourly_signal_names.csv"), index=False)
    print(tag, "DONE tests", tests, "signals", N, "candidates", len(R), flush=True)


if __name__ == "__main__":
    run(null=len(sys.argv) > 1 and sys.argv[1] == "null", seed=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
