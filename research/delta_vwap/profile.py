"""Block 4 - volume profile.
Profiles: volume of every 1-minute bar spread evenly over its ticks (L..H), per Globex day; composites = sum of
daily profiles (previous week, previous month, previous 20 days). POC = price with the most volume, value area 70 %.
A  magnet test: probability that today's RTH session touches the previous day / week / month POC vs a control level
   at the same distance on the other side of the RTH open (a real magnet should be hit more often)
B  naked POCs (daily POCs untouched since they formed, age 2-20 days): touch rate vs control level
C  POC + cumulative delta: first touch of the previous day POC from above / below in RTH, split by the change of
   CD over the last 30 minutes (absorption = price into POC while CD moves the other way) -> trade away from POC
D  80 % rule on daily / weekly / monthly value areas: RTH opens outside the previous value area, then two 30-minute
   closes inside -> probability of reaching the other side of the value area
E  low- vs high-volume nodes of the 20-day composite: at every half hour of RTH, volume density at the price
   (percentile of the composite) -> absolute move and continuation over the next 60 minutes
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prep as P
from trade import summarize

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


@njit(cache=True)
def day_hist(Lt, Ht, V, lo, n):
    h = np.zeros(n)
    for i in range(len(Lt)):
        k = Ht[i] - Lt[i] + 1
        v = V[i] / k
        for t in range(Lt[i], Ht[i] + 1):
            h[t - lo] += v
    return h


def poc_va(h, lo):
    p = int(np.argmax(h)); tot = h.sum(); a = b = p; s = h[p]
    while s < 0.7 * tot:
        up = h[b + 1] if b + 1 < len(h) else -1
        dn = h[a - 1] if a - 1 >= 0 else -1
        if up >= dn:
            b += 1; s += up
        else:
            a -= 1; s += dn
    return (lo + p) / 4, (lo + b) / 4, (lo + a) / 4      # poc, vah, val (points)


def build_profiles(f):
    Lt = (f.L.to_numpy() * 4).round().astype(np.int64); Ht = (f.H.to_numpy() * 4).round().astype(np.int64)
    V = f.V.to_numpy()
    days, start = np.unique(f.gday.to_numpy(), return_index=True)
    bounds = np.r_[start, len(f)]
    prof = []
    for k in range(len(days)):
        a, b = bounds[k], bounds[k + 1]
        lo = Lt[a:b].min(); hi = Ht[a:b].max()
        prof.append((lo, day_hist(Lt[a:b], Ht[a:b], V[a:b], lo, hi - lo + 1)))
    return days, prof


def composite(prof, ks):
    lo = min(prof[k][0] for k in ks); hi = max(prof[k][0] + len(prof[k][1]) for k in ks)
    h = np.zeros(hi - lo)
    for k in ks:
        l, a = prof[k]
        h[l - lo:l - lo + len(a)] += a
    return lo, h


def levels(f, days, prof):
    """per day: previous day / previous week / previous month / previous 20 days POC, VAH, VAL"""
    dts = pd.DatetimeIndex(days)
    wk = (dts - pd.to_timedelta(dts.day_of_week, unit="D")).to_numpy()
    mo = dts.to_period("M").astype(str).to_numpy()
    rows = []
    for k in range(len(days)):
        r = {"gday": days[k]}
        if k >= 1:
            r["d_poc"], r["d_vah"], r["d_val"] = poc_va(prof[k - 1][1], prof[k - 1][0])
        prevw = [j for j in range(max(0, k - 10), k) if wk[j] != wk[k]]
        if prevw:
            last = wk[prevw[-1]]; ks = [j for j in prevw if wk[j] == last]
            lo, h = composite(prof, ks); r["w_poc"], r["w_vah"], r["w_val"] = poc_va(h, lo)
        prevm = [j for j in range(max(0, k - 30), k) if mo[j] != mo[k]]
        if prevm:
            last = mo[prevm[-1]]; ks = [j for j in prevm if mo[j] == last]
            lo, h = composite(prof, ks); r["m_poc"], r["m_vah"], r["m_val"] = poc_va(h, lo)
        rows.append(r)
    return pd.DataFrame(rows).set_index("gday")


def rth_days(f):
    r = f[f.rth]
    g = r.groupby("gday").agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"), atr=("atr", "first"))
    return r, g


def part_A(g, lv):
    rows = []
    for name in ("d", "w", "m"):
        x = g.join(lv[[f"{name}_poc"]]).dropna()
        poc = x[f"{name}_poc"]; ctrl = 2 * x.O - poc
        dist = (poc - x.O).abs() / x.atr
        for lo_, hi_ in ((0, 0.25), (0.25, 0.5), (0.5, 1), (1, 2)):
            m = (dist > lo_) & (dist <= hi_)
            hit = ((x.L <= poc) & (x.H >= poc))[m]; hc = ((x.L <= ctrl) & (x.H >= ctrl))[m]
            rows.append(dict(poc={"d": "predchozi den", "w": "predchozi tyden", "m": "predchozi mesic"}[name],
                             vzdalenost_atr=f"{lo_}-{hi_}", dnu=int(m.sum()), p_dotyk_poc=hit.mean(),
                             p_dotyk_kontrola=hc.mean(), rozdil=hit.mean() - hc.mean(),
                             t=(hit.mean() - hc.mean()) / np.sqrt((hit.var() + hc.var()) / max(m.sum(), 1))))
    A = pd.DataFrame(rows); A.round(4).to_csv(os.path.join(OUT, "H_poc_magnet.csv"), index=False)
    return A


def part_B(g, days, prof):
    """naked daily POCs: for each day the set of earlier POCs (2-20 days old) not touched since"""
    pocs = np.array([poc_va(h, lo)[0] for lo, h in prof])
    gi = g.reindex(pd.DatetimeIndex(days))
    H = gi.H.to_numpy(); L = gi.L.to_numpy(); O = gi.O.to_numpy(); atr = gi.atr.to_numpy()
    # full Globex range per day for 'touched since'
    Hg = np.array([(lo + len(h) - 1) / 4 for lo, h in prof]); Lg = np.array([lo / 4 for lo, h in prof])
    rows = []
    for k in range(21, len(days)):
        if not np.isfinite(O[k]):
            continue
        for age in range(2, 21):
            j = k - age
            p = pocs[j]
            touched = np.any((Lg[j + 1:k] <= p) & (Hg[j + 1:k] >= p))
            if touched:
                continue
            d = abs(p - O[k]) / atr[k]
            if d > 2:
                continue
            c = 2 * O[k] - p
            rows.append(dict(vek=age, vzd=d, hit=(L[k] <= p) & (H[k] >= p), hc=(L[k] <= c) & (H[k] >= c)))
    X = pd.DataFrame(rows)
    X["vek_skup"] = pd.cut(X.vek, [1, 3, 5, 10, 20]).astype(str)
    X["vzd_skup"] = pd.cut(X.vzd, [0, 0.25, 0.5, 1, 2]).astype(str)
    B = X.groupby(["vek_skup", "vzd_skup"]).agg(n=("hit", "size"), p_dotyk_naked_poc=("hit", "mean"),
                                                p_dotyk_kontrola=("hc", "mean")).reset_index()
    B["rozdil"] = B.p_dotyk_naked_poc - B.p_dotyk_kontrola
    B.round(4).to_csv(os.path.join(OUT, "I_naked_poc.csv"), index=False)
    return B


def part_C(f, lv, end):
    """first RTH touch of the previous day POC, from above (long) / from below (short), split by CD change 30 min"""
    rows = []
    poc = f.gday.map(lv.d_poc).to_numpy()
    C = f.C.to_numpy(); H = f.H.to_numpy(); L = f.L.to_numpy(); atr = f.atr.to_numpy()
    cd = f.cd_g.to_numpy(); dcd = cd - np.r_[np.full(30, np.nan), cd[:-30]]
    dp = C - np.r_[np.full(30, np.nan), C[:-30]]
    rth = f.rth.to_numpy() & (f["mod"].to_numpy() <= 930)
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    prevC = np.r_[np.nan, C[:-1]]
    for side in (1, -1):
        touch = (L <= poc) & (prevC > poc) if side == 1 else (H >= poc) & (prevC < poc)
        m = touch & rth
        idx = np.flatnonzero(m & (pd.Series(m).groupby(dpos).cumsum().to_numpy() == 1))
        groups = {"vse": np.ones(len(idx), bool),
                  "CD proti pohybu ceny (absorpce)": (np.sign(dcd[idx]) == side) & (np.sign(dp[idx]) == -side),
                  "CD ve smeru pohybu ceny": np.sign(dcd[idx]) == -side,
                  "CD roste": dcd[idx] > 0, "CD klesa": dcd[idx] < 0,
                  "denni CD > 0": cd[idx] > 0, "denni CD < 0": cd[idx] < 0}
        for gname, gm in groups.items():
            sel = idx[gm]
            e = poc[sel]
            for tpk, slk in ((0.25, 0.25), (0.5, 0.25), (0.25, 0.5)):
                r = summarize(f"POC vcerejska {'long z vrchu' if side == 1 else 'short zespodu'} | {gname} | TP{tpk}/SL{slk} ATR",
                              f, sel, np.full(len(sel), side), C[sel] + side * tpk * atr[sel],
                              C[sel] - side * slk * atr[sel], end[sel],
                              dict(smer="long" if side == 1 else "short", skupina=gname, TP_atr=tpk, SL_atr=slk))
                if r:
                    rows.append(r)
    R = pd.DataFrame(rows); R.round(4).to_csv(os.path.join(OUT, "J_poc_delta.csv"), index=False)
    return R


def part_D(f, lv):
    """80 % rule: RTH open outside the previous value area, two consecutive 30-minute closes back inside"""
    r = f[f.rth]
    rows = []
    for name in ("d", "w", "m"):
        vah = r.gday.map(lv[f"{name}_vah"]).to_numpy(); val = r.gday.map(lv[f"{name}_val"]).to_numpy()
        res = []
        for gd, g in r.assign(vah=vah, val=val).groupby("gday"):
            o = g.O.iloc[0]; a = g.vah.iloc[0]; b = g.val.iloc[0]
            if not np.isfinite(a) or (b <= o <= a):
                continue
            above = o > a
            c30 = g.C.to_numpy()[29::30]
            inside = (c30 <= a) & (c30 >= b)
            hit_i = None
            for k in range(1, len(inside)):
                if inside[k] and inside[k - 1]:
                    hit_i = (k + 1) * 30; break
            if hit_i is None:
                res.append(dict(signal=False)); continue
            rest = g.iloc[hit_i:]
            target = b if above else a
            reached = (rest.L.min() <= target) if above else (rest.H.max() >= target)
            res.append(dict(signal=True, reached=reached, vzd=abs(g.C.iloc[hit_i - 1] - target) / g.atr.iloc[0]))
        X = pd.DataFrame(res)
        s = X[X.signal]
        rows.append(dict(value_area={"d": "predchozi den", "w": "predchozi tyden", "m": "predchozi mesic"}[name],
                         dnu_open_mimo_VA=len(X), signalu=len(s), podil_signalu=len(s) / len(X),
                         p_druha_strana_VA=s.reached.mean(), prumerna_vzdalenost_atr=s.vzd.mean()))
    D = pd.DataFrame(rows); D.round(4).to_csv(os.path.join(OUT, "K_80_procent.csv"), index=False)
    return D


def part_E(f, days, prof):
    """volume density at the price in the previous-20-day composite (percentile among the composite's ticks)"""
    r = f[f.rth & (f["mod"] % 30 == 0) & (f["mod"] <= 900)].copy()
    dmap = {d: k for k, d in enumerate(days)}
    dens = np.full(len(r), np.nan)
    gk = r.gday.map(dmap).to_numpy()
    Ct = (r.C.to_numpy() * 4).round().astype(np.int64)
    for k in np.unique(gk):
        if k < 20:
            continue
        lo, h = composite(prof, range(k - 20, k))
        ranks = h.argsort().argsort() / (len(h) - 1)
        sel = np.flatnonzero(gk == k)
        pos = Ct[sel] - lo
        ok = (pos >= 0) & (pos < len(h))
        dens[sel[ok]] = ranks[pos[ok]]
    r["hustota"] = dens
    C = f.C.to_numpy()
    j = np.minimum(r.index.to_numpy() + 60, len(f) - 1)
    r["abs60"] = np.abs(C[j] - r.C.to_numpy()) / r.atr
    prev = r.index.to_numpy() - 30
    r["dir30"] = np.sign(r.C.to_numpy() - C[prev])
    r["pokr60"] = (C[j] - r.C.to_numpy()) * r.dir30 / r.atr
    r["mimo"] = r.hustota.isna()
    r["skupina"] = pd.cut(r.hustota, [-0.01, 0.2, 0.4, 0.6, 0.8, 1.0],
                          labels=["LVN (0-20 %)", "20-40 %", "40-60 %", "60-80 %", "HVN (80-100 %)"]).astype(str)
    r.loc[r.mimo, "skupina"] = "mimo 20denni profil"
    E = r.groupby("skupina").agg(n=("abs60", "size"), pohyb_60m_atr=("abs60", "mean"),
                                 pokracovani_60m_atr=("pokr60", "mean"),
                                 p_pokracovani=("pokr60", lambda x: (x > 0).mean())).reset_index()
    E.round(4).to_csv(os.path.join(OUT, "L_lvn_hvn.csv"), index=False)
    return E


if __name__ == "__main__":
    import time
    f = P.load()
    from vwap import day_end
    end, _ = day_end(f)
    t = time.time(); days, prof = build_profiles(f); print("profiles", round(time.time() - t), flush=True)
    lv = levels(f, days, prof); lv.to_parquet(os.path.join(P.CACHE, "levels.parquet")); print("levels", flush=True)
    r, g = rth_days(f)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(part_A(g, lv).round(3).to_string(), flush=True)
    print(part_B(g, days, prof).round(3).to_string(), flush=True)
    cols = ["test", "n", "win", "nahodna_win", "hrube_b", "cisty_b", "t", "cisty_2011_18", "cisty_2019_26"]
    print(part_C(f, lv, end)[cols].round(3).to_string(), flush=True)
    print(part_D(f, lv).round(3).to_string(), flush=True)
    print(part_E(f, days, prof).round(3).to_string(), flush=True)
