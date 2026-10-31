"""H3 / H4: sharp move (impulse) -> multi-hour pause -> what next.

Impulse: |close - close 30 min ago| >= thr x daily ATR. Pause: the next P minutes (same Globex day) stay inside a range
<= pr x ATR. Event time = end of the pause (only past data is used to detect it). Outcome (drift-balanced: the mean of
up impulses and down impulses):
 * race: starting from the end of the pause, which comes first within 1 day (or 5 days): the origin of the impulse (price
   30 min before it, 'reversal') or the extension of the same distance D on the other side ('continuation').
   Random walk without drift = 50 %.
 * excess move in the impulse direction at 2h / 12h / 1d / 2d (ATR) over the mean of the same year x minute of the day.
Splits: impulse toward or away from the weekly VWAP, price inside / above / below the previous week's 70 % value area,
distance from the weekly VWAP (ATR), session of the event. Selection 2011-18, test 2019-26, 2-week block clusters.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "/home/user/Lukacino/research/delta_vwap")
import prep as P

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
HZ = {"2h": 120, "12h": 720, "1d": 1380, "2d": 2760}


@njit(cache=True)
def episodes(C, H, L, atr, gd, thr, P_, pr, lb):
    n = len(C); ej = []; ee = []; ed = []
    last = -1; j = lb
    while j < n - P_ - 1:
        if j > last and atr[j] > 0 and gd[j] == gd[j - lb] and gd[j + P_] == gd[j]:
            mv = C[j] - C[j - lb]
            if abs(mv) >= thr * atr[j]:
                hi = -1e18; lo = 1e18
                for k in range(j + 1, j + P_ + 1):
                    if H[k] > hi: hi = H[k]
                    if L[k] < lo: lo = L[k]
                if hi - lo <= pr * atr[j]:
                    ej.append(j); ee.append(j + P_); ed.append(1 if mv > 0 else -1)
                    last = j + P_; j = j + P_
                    continue
        j += 1
    return np.array(ej), np.array(ee), np.array(ed)


@njit(cache=True)
def race(H, L, e, up, dn, maxb):
    n = len(H); out = np.zeros(len(e), np.int8)
    for k in range(len(e)):
        for j in range(e[k] + 1, min(e[k] + maxb, n - 1) + 1):
            hu = H[j] >= up[k]; hd = L[j] <= dn[k]
            if hu and hd:
                break
            if hu:
                out[k] = 1; break
            if hd:
                out[k] = -1; break
    return out


def balanced(x, d, blk, mask):
    ok = mask & np.isfinite(x)
    if ok.sum() < 30 or len(np.unique(d[ok])) < 2:
        return np.nan, np.nan, int(ok.sum())
    df = pd.DataFrame({"d": d[ok], "blk": blk[ok], "x": x[ok]})
    g = df.groupby("d").x
    df["mu"] = g.transform("mean"); df["w"] = 0.5 / g.transform("size")
    eff = (df.w * df.x).sum()
    e = (df.w * (df.x - df.mu)).groupby(df.blk).sum()
    return eff, float(np.sqrt((e ** 2).sum())), int(ok.sum())


def main():
    f = P.load(); n = len(f)
    C = f.C.to_numpy(); H = f.H.to_numpy(); L = f.L.to_numpy(); atr = f.atr.to_numpy()
    mod = f["mod"].to_numpy(); year = f.ts.dt.year.to_numpy()
    gd = f.gday.to_numpy().astype("datetime64[D]").astype(np.int64)
    lv = pd.read_parquet(os.path.join(P.CACHE, "levels.parquet"))
    wval = f.gday.map(lv.w_val).to_numpy(); wvah = f.gday.map(lv.w_vah).to_numpy(); vw = f.vwap_w.to_numpy()
    ts = f.ts.to_numpy()
    base = {}
    for h, b in HZ.items():
        fw = np.where(np.arange(n) + b < n, (np.r_[C[b:], np.full(b, np.nan)] - C) / atr, np.nan)
        base[h] = (fw, pd.Series(fw).groupby([year, mod]).transform("mean").to_numpy())
    rows = []
    for thr, P_, pr in itertools.product((0.3, 0.5, 0.75), (60, 120, 180), (0.2, 0.35)):
        ej, ee, ed = episodes(C, H, L, np.nan_to_num(atr), gd, thr, P_, pr, 30)
        if len(ee) < 100:
            continue
        origin = C[ej - 30]; D = np.abs(C[ee] - origin)
        up_lvl = np.where(ed == 1, C[ee] + D, origin); dn_lvl = np.where(ed == 1, origin, C[ee] - D)
        r1 = race(H, L, ee, up_lvl, dn_lvl, 1380); r5 = race(H, L, ee, up_lvl, dn_lvl, 6900)
        # reversal = origin first: up impulse -> lower level first (-1); down impulse -> upper first (+1)
        rev1 = np.where(r1 == 0, np.nan, (r1 == -ed).astype(float)); rev5 = np.where(r5 == 0, np.nan, (r5 == -ed).astype(float))
        blk = (gd[ee] // 14)
        disc = ts[ee] < np.datetime64("2019-01-01")
        on_dir_side = ((ed == 1) & (C[ee] > vw[ee])) | ((ed == -1) & (C[ee] < vw[ee]))
        vdist = np.abs(C[ee] - vw[ee]) / atr[ee]
        inside = (C[ee] >= wval[ee]) & (C[ee] <= wvah[ee])
        above = C[ee] > wvah[ee]; below = C[ee] < wval[ee]
        sess = np.where((mod[ee] >= 1080) | (mod[ee] < 180), 0, np.where(mod[ee] < 570, 1, 2))
        splits = {"vse": np.ones(len(ee), bool), "impuls od W-VWAP pryc": on_dir_side, "impuls k W-VWAP": ~on_dir_side,
                  "uvnitr VA minuleho tydne": inside, "nad VAH": above, "pod VAL": below,
                  "vzdalenost od W-VWAP <0.5 ATR": vdist < 0.5, "0.5-1 ATR": (vdist >= 0.5) & (vdist < 1), ">1 ATR": vdist >= 1,
                  "Asie": sess == 0, "Evropa": sess == 1, "USA": sess == 2}
        metrics = {"reverzni zavod 1d (origin driv)": rev1 - 0.5, "reverzni zavod 5d": rev5 - 0.5}
        for h, (fw, b) in base.items():
            idx = np.minimum(ee, n - 1)
            metrics[f"pokracovani {h} (ATR)"] = (fw[idx] - b[idx]) * ed
        for sname, sm in splits.items():
            for mname, x in metrics.items():
                eff, se, nn = balanced(x, ed, blk, sm)
                e1, s1, n1 = balanced(x, ed, blk, sm & disc); e2, s2, n2 = balanced(x, ed, blk, sm & ~disc)
                rows.append(dict(impuls_ATR=thr, pauza_min=P_, rozsah_pauzy_ATR=pr, podminka=sname, mereni=mname, udalosti=nn,
                                 efekt=eff, se=se, t=eff / se if se and se > 0 else np.nan, efekt_2011_18=e1, efekt_2019_26=e2))
        print(thr, P_, pr, len(ee), "udalosti; reverze 1d:", round(float(np.nanmean(rev1)), 3), flush=True)
    T = pd.DataFrame(rows)
    T.round(4).to_csv(os.path.join(OUT, "G_impuls_pauza.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print("testu", len(T), " |t|>2:", (T.t.abs() > 2).mean().round(3), " |t|>3:", (T.t.abs() > 3).sum())
    print(T[T.podminka == "vse"].groupby("mereni")[["efekt", "t"]].agg(["mean", "min", "max"]).round(3).to_string())
    print(T.sort_values("t", key=lambda s: -s.abs()).head(12)[["impuls_ATR", "pauza_min", "rozsah_pauzy_ATR", "podminka", "mereni", "udalosti", "efekt", "t", "efekt_2011_18", "efekt_2019_26"]].round(3).to_string())
    c = T.dropna(subset=["efekt_2011_18", "efekt_2019_26"])
    print("stabilita: corr", c.efekt_2011_18.corr(c.efekt_2019_26).round(3), " stejne znamenko", ((c.efekt_2011_18 * c.efekt_2019_26) > 0).mean().round(3))


if __name__ == "__main__":
    main()
