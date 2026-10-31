"""Target & time-to-hit test of price anchors (modules 5 + 6 of the ACSIL brief).

Events: every full hour (24 h) when the close is 0.1-4 daily ATR away from an anchor. Anchors (all known at the close
of the event bar): daily / weekly / monthly VWAP, previous day / week / month POC, VAH, VAL (70 % value area of the
volume profile, not SD bands), previous day high and low.
Trade T ('toward'): target = anchor, stop = s ATR against, horizon H. Control A ('away'): the mirror level at the same
distance on the other side of the price, same stops. The difference T - A is the effect of the anchor; the mirror
removes volatility and time-of-day, and what remains is the drift (long bias).
Measures: P(target hit within H), max adverse excursion (MAE) before the hit, share of stop-outs before the hit,
net expectancy in points (cost 0.5 point per trade, a stop and the target on the same bar count as a stop), per
horizon 2h / 3h / 12h / 1d / 2d / 5d / end of the Globex RTH day. Selection on 2011-18, test 2019-26.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

sys.path.insert(0, "/home/user/Lukacino/research/delta_vwap")
import prep as P

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
COST = 0.5
HOR = {"2h": 120, "3h": 180, "12h": 720, "1d": 1380, "2d": 2760, "5d": 6900}
STOPS = (0.5, 1.0, 2.0)
MAXH = 6900
BUCKETS = [(0.1, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 4.0)]
SESS = {0: "Asie 18-03", 1: "Evropa 03-09:30", 2: "USA 09:30-17"}


@njit(parallel=True, cache=True)
def scan(H, L, C, idx, level, dirn, atr, stops):
    m = len(idx); n = len(C)
    t_hit = -np.ones(m, np.int32); mae = np.zeros(m, np.float32)
    t_st = -np.ones((m, len(stops)), np.int32)
    for k in prange(m):
        i = idx[k]; e = C[i]; a = atr[k]; lv = level[k]; d = dirn[k]
        end = min(i + MAXH, n - 1); worst = 0.0
        for j in range(i + 1, end + 1):
            adv = (e - L[j]) if d == 1 else (H[j] - e)
            if adv > worst:
                worst = adv
            for s in range(len(stops)):
                if t_st[k, s] < 0 and adv >= stops[s] * a:
                    t_st[k, s] = j - i
            hit = (H[j] >= lv) if d == 1 else (L[j] <= lv)
            if hit:
                t_hit[k] = j - i; break
        mae[k] = worst / a
    return t_hit, mae, t_st


def anchors(f):
    lv = pd.read_parquet(os.path.join(P.CACHE, "levels.parquet"))
    out = {"VWAP denni": f.vwap_d.to_numpy(), "VWAP tydenni": f.vwap_w.to_numpy(), "VWAP mesicni": f.vwap_m.to_numpy()}
    for k, nm in (("d", "predchozi den"), ("w", "predchozi tyden"), ("m", "predchozi mesic")):
        for c, cn in (("poc", "POC"), ("vah", "VAH"), ("val", "VAL")):
            out[f"{cn} {nm}"] = f.gday.map(lv[f"{k}_{c}"]).to_numpy()
    g = f.groupby("gday").agg(H=("H", "max"), L=("L", "min"))
    out["High predchoziho dne"] = f.gday.map(g.H.shift(1)).to_numpy()
    out["Low predchoziho dne"] = f.gday.map(g.L.shift(1)).to_numpy()
    return out


def session_id(mod):
    return np.where((mod >= 1080) | (mod < 180), 0, np.where(mod < 570, 1, 2))


def day_end_index(f):
    idx = np.arange(len(f)); mod = f["mod"].to_numpy()
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    cb = pd.Series(np.where((mod >= 570) & (mod <= 959), idx, -1)).groupby(dpos).max().to_numpy()
    return cb[dpos]


def build(f):
    n = len(f)
    C = f.C.to_numpy(); H = f.H.to_numpy(); L = f.L.to_numpy(); atr_all = f.atr.to_numpy()
    mod = f["mod"].to_numpy()
    base = np.flatnonzero((mod % 60 == 0) & np.isfinite(atr_all) & (np.arange(n) < n - 10))
    A = anchors(f)
    rows = []
    for name, arr in A.items():
        lvl = arr[base]; ok = np.isfinite(lvl)
        i = base[ok]; lv = lvl[ok]
        d_pts = np.abs(lv - C[i]); atr = atr_all[i]
        dd = d_pts / atr
        sel = (dd >= 0.1) & (dd < 4.0)
        i = i[sel]; lv = lv[sel]; atr = atr[sel]; dd = dd[sel]
        dirn = np.where(lv > C[i], 1, -1).astype(np.int64)
        rows.append(pd.DataFrame({"anchor": name, "i": i, "level": lv, "dir": dirn, "atr": atr, "d_atr": dd}))
    E = pd.concat(rows, ignore_index=True)
    stops = np.array(STOPS)
    res = {}
    for side in ("T", "A"):
        if side == "T":
            lvl = E.level.to_numpy(); dr = E.dir.to_numpy()
        else:
            lvl = (2 * C[E.i.to_numpy()] - E.level.to_numpy()); dr = -E.dir.to_numpy()
        th, mae, ts = scan(H, L, C, E.i.to_numpy().astype(np.int64), lvl, dr.astype(np.int64), E.atr.to_numpy(), stops)
        res[side] = dict(t_hit=th, mae=mae, t_st=ts, dir=dr, level=lvl)
    return E, res


def evaluate(f, E, res, tag_cols=("anchor", "bucket")):
    C = f.C.to_numpy(); n = len(C)
    ii = E.i.to_numpy()
    day = f.gday.to_numpy()[ii]; ts = f.ts.to_numpy()[ii]
    disc = ts < np.datetime64("2019-01-01")
    dayend = day_end_index(f)[ii]
    ends = {h: np.minimum(ii + b, n - 1) for h, b in HOR.items()}
    ends["dnes RTH close"] = np.where(dayend > ii, dayend, np.minimum(ii + 1380, n - 1))
    atr = E.atr.to_numpy()
    out = {}
    for side in ("T", "A"):
        r = res[side]
        dpts = np.abs(r["level"] - C[ii])
        for h, e in ends.items():
            Hb = e - ii
            hit_ok = (r["t_hit"] >= 0) & (r["t_hit"] <= Hb)
            for si, s in enumerate(list(STOPS) + [None]):
                if s is None:
                    stop_ok = np.zeros(len(ii), bool); tst = np.full(len(ii), 10 ** 9)
                else:
                    tst = r["t_st"][:, si]
                    stop_ok = (tst >= 0) & (tst <= Hb)
                    tst = np.where(tst >= 0, tst, 10 ** 9)
                th = np.where(r["t_hit"] >= 0, r["t_hit"], 10 ** 9)
                stop_first = stop_ok & (tst <= th)
                win = hit_ok & ~stop_first
                open_ = ~win & ~stop_first
                pnl = np.where(win, dpts, np.where(stop_first, -(s if s else 0) * atr, (C[e] - C[ii]) * r["dir"]))
                out[(side, h, s)] = (pnl - COST, win, stop_first, hit_ok)
    return out, day, disc, ends


def summarize(f, E, res):
    out, day, disc, ends = evaluate(f, E, res)
    E = E.copy()
    E["bucket"] = pd.cut(E.d_atr, [b[0] for b in BUCKETS] + [4.0], right=False,
                         labels=[f"{a}-{b}" for a, b in BUCKETS]).astype(str)
    ev_rows = []; hit_rows = []
    keys = E.groupby(["anchor", "bucket"]).indices
    for (an, bk), ix in keys.items():
        if len(ix) < 200:
            continue
        days = day[ix]; dz = disc[ix]
        for h in list(HOR) + ["dnes RTH close"]:
            hitT = out[("T", h, None)][3][ix]; hitA = out[("A", h, None)][3][ix]
            dif = pd.Series((hitT.astype(float) - hitA)).groupby(days).mean()
            t = dif.mean() / dif.std() * np.sqrt(len(dif)) if dif.std() > 0 else np.nan
            mae = res["T"]["mae"][ix][hitT & (res["T"]["t_hit"][ix] <= (ends[h][ix] - E.i.to_numpy()[ix]))]
            hit_rows.append(dict(kotva=an, vzdalenost_atr=bk, horizont=h, udalosti=len(ix), dnu=len(dif),
                                 p_dosazeni=hitT.mean(), p_dosazeni_zrcadlo=hitA.mean(), rozdil=hitT.mean() - hitA.mean(), t=t,
                                 MAE_median_atr=np.median(mae) if len(mae) else np.nan,
                                 MAE_p90_atr=np.quantile(mae, 0.9) if len(mae) else np.nan))
            for s in list(STOPS) + [None]:
                nt, wt, st, _ = out[("T", h, s)]; na = out[("A", h, s)][0]
                nt = nt[ix]; na = na[ix]
                dd = pd.Series(nt - na).groupby(days).mean()
                tt = pd.Series(nt).groupby(days).mean()
                ev_rows.append(dict(kotva=an, vzdalenost_atr=bk, horizont=h, stop_atr=s if s else "bez stopu",
                                    udalosti=len(ix), dnu=len(tt), win_T=wt[ix].mean(), stop_driv_T=st[ix].mean(),
                                    EV_T_cisty_b=nt.mean(), EV_zrcadlo_cisty_b=na.mean(),
                                    t_EV_T=tt.mean() / tt.std() * np.sqrt(len(tt)) if tt.std() > 0 else np.nan,
                                    t_T_minus_zrcadlo=dd.mean() / dd.std() * np.sqrt(len(dd)) if dd.std() > 0 else np.nan,
                                    EV_2011_18=nt[dz].mean() if dz.any() else np.nan,
                                    EV_2019_26=nt[~dz].mean() if (~dz).any() else np.nan,
                                    n_2011_18=int(dz.sum()), n_2019_26=int((~dz).sum())))
    return pd.DataFrame(hit_rows), pd.DataFrame(ev_rows), E


def sessions(f, E, res):
    sid = session_id(f["mod"].to_numpy())
    ii = E.i.to_numpy(); C = f.C.to_numpy()
    grp = np.where(E.anchor.str.startswith("VWAP"), "VWAP", np.where(E.anchor.str.contains("High|Low"), "High/Low dne", "profil (POC/VAH/VAL)"))
    out, day, disc, ends = evaluate(f, E, res)
    rows = []
    for g in np.unique(grp):
        for s in (0, 1, 2):
            ix = np.flatnonzero((grp == g) & (sid[ii] == s) & (E.d_atr.to_numpy() >= 0.25) & (E.d_atr.to_numpy() < 2))
            if len(ix) < 300:
                continue
            for h in ("2h", "12h", "1d", "5d"):
                hitT = out[("T", h, None)][3][ix]; hitA = out[("A", h, None)][3][ix]
                nt = out[("T", h, 1.0)][0][ix]; na = out[("A", h, 1.0)][0][ix]
                rows.append(dict(skupina_kotev=g, seance_udalosti=SESS[s], horizont=h, udalosti=len(ix),
                                 p_dosazeni=hitT.mean(), p_zrcadlo=hitA.mean(), rozdil=hitT.mean() - hitA.mean(),
                                 EV_stop1ATR_b=nt.mean(), EV_zrcadlo_b=na.mean()))
        # where do hits happen (1d horizon): session of the hit bar vs the session of the event
        for s in (0, 1, 2):
            ix = np.flatnonzero((grp == g) & (sid[ii] == s) & (E.d_atr.to_numpy() >= 0.25) & (E.d_atr.to_numpy() < 2)
                                & (res["T"]["t_hit"] >= 0) & (res["T"]["t_hit"] <= 1380))
            if len(ix) < 200:
                continue
            hb = ii[ix] + res["T"]["t_hit"][ix]
            same_day = f.gday.to_numpy()[hb] == f.gday.to_numpy()[ii[ix]]
            rows.append(dict(skupina_kotev=g, seance_udalosti=SESS[s], horizont="kde se dosahne (1d)", udalosti=len(ix),
                             p_dosazeni=(sid[hb] == s).mean(), p_zrcadlo=np.nan,
                             rozdil=same_day.mean(), EV_stop1ATR_b=np.nan, EV_zrcadlo_b=np.nan,
                             ))
    R = pd.DataFrame(rows)
    return R


if __name__ == "__main__":
    import time
    t = time.time()
    f = P.load(); E, res = build(f)
    print("events", len(E), round(time.time() - t), "s", flush=True)
    Hh, Ev, E2 = summarize(f, E, res)
    Hh.round(4).to_csv(os.path.join(OUT, "A_dosazeni_kotev.csv"), index=False)
    Ev.round(4).to_csv(os.path.join(OUT, "B_ev_kotev.csv"), index=False)
    S = sessions(f, E2, res); S.round(4).to_csv(os.path.join(OUT, "C_seance.csv"), index=False)
    E2.to_parquet(os.path.join(P.CACHE, "anchor_events.parquet"))
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print(round(time.time() - t), "s", len(Hh), len(Ev))
    h = Hh[Hh.horizont.isin(["2h", "1d", "5d"])]
    print(h.groupby(["horizont"])[["p_dosazeni", "p_dosazeni_zrcadlo", "rozdil"]].mean().round(3))
