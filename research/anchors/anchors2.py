"""Anchors, corrected significance: placebo anchors and week clusters.

anchors.py compared the hit rate of the anchor with a mirror level; that is right for the vol / time-of-day control
but the day-clustered t-statistics are inflated (hourly events, horizons up to 5 days overlap across days).
Here: (1) clusters are calendar weeks, (2) placebo anchors: the signed offset (anchor - close) / ATR of the same anchor
type taken from a random earlier day (5-60 trading days) is applied to the current close, so the placebo has the same
distribution of distances and sides but no link to the real structure. Effect of the anchor = real - placebo, paired
by week. 3 placebo draws.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors as AN
from anchors import HOR, STOPS, BUCKETS, COST, OUT, scan, anchors as get_anchors, day_end_index
sys.path.insert(0, "/home/user/Lukacino/research/delta_vwap")
import prep as P

HNAMES = list(HOR) + ["dnes RTH close"]
SNAMES = list(STOPS) + [None]


def make_events(f, A, shift, rng):
    n = len(f)
    C = f.C.to_numpy(); atr_all = f.atr.to_numpy(); mod = f["mod"].to_numpy()
    base = np.flatnonzero((mod % 60 == 0) & np.isfinite(atr_all) & (np.arange(n) < n - 10) & (np.arange(n) > 1380 * 70))
    rows = []
    for name, arr in A.items():
        i = base
        j = i - (rng.integers(5, 61, len(i)) * 1380 if shift else 0)
        off = arr[j] - C[j]
        ok = np.isfinite(off) & np.isfinite(atr_all[j])
        i = i[ok]; j = j[ok]; off = off[ok]
        dd = np.abs(off) / atr_all[j]
        sel = (dd >= 0.1) & (dd < 4.0)
        i = i[sel]; j = j[sel]; off = off[sel]; dd = dd[sel]
        lvl = C[i] + off * atr_all[i] / atr_all[j]
        rows.append(pd.DataFrame({"anchor": name, "i": i, "level": lvl, "dir": np.where(off > 0, 1, -1), "atr": atr_all[i],
                                  "d_atr": dd}))
    E = pd.concat(rows, ignore_index=True)
    E["bucket"] = pd.cut(E.d_atr, [b[0] for b in BUCKETS] + [4.0], right=False,
                         labels=[f"{a}-{b}" for a, b in BUCKETS]).astype(str)
    return E


def outcomes(f, E, mirror=False):
    C = f.C.to_numpy(); H = f.H.to_numpy(); L = f.L.to_numpy(); n = len(C)
    ii = E.i.to_numpy().astype(np.int64)
    if mirror:
        lvl = 2 * C[ii] - E.level.to_numpy(); dr = -E["dir"].to_numpy()
    else:
        lvl = E.level.to_numpy(); dr = E["dir"].to_numpy()
    th, mae, ts = scan(H, L, C, ii, lvl, dr.astype(np.int64), E.atr.to_numpy(), np.array(STOPS))
    dayend = day_end_index(f)[ii]
    ends = {h: np.minimum(ii + b, n - 1) for h, b in HOR.items()}
    ends["dnes RTH close"] = np.where(dayend > ii, dayend, np.minimum(ii + 1380, n - 1))
    dpts = np.abs(lvl - C[ii]); atr = E.atr.to_numpy()
    hit = {}; net = {}
    thh = np.where(th >= 0, th, 10 ** 9)
    for h, e in ends.items():
        Hb = e - ii
        hit[h] = ((th >= 0) & (th <= Hb)).astype(np.float32)
        for si, s in enumerate(SNAMES):
            if s is None:
                stop_first = np.zeros(len(ii), bool)
            else:
                tst = ts[:, si]
                stop_first = (tst >= 0) & (tst <= Hb) & (np.where(tst >= 0, tst, 10 ** 9) <= thh)
            win = (hit[h] > 0) & ~stop_first
            pnl = np.where(win, dpts, np.where(stop_first, -(s or 0) * atr, (C[e] - C[ii]) * dr))
            net[(h, s)] = (pnl - COST).astype(np.float32)
    return hit, net, mae, th


def week_of(f, E):
    g = f.gday.to_numpy()[E.i.to_numpy()]
    return (g.astype("datetime64[D]").astype(np.int64) // 7)


def weekly(E, wk, vals):
    return pd.Series(vals).groupby([E.anchor.to_numpy(), E.bucket.to_numpy(), wk]).mean()


def main():
    f = P.load(); A = get_anchors(f); rng = np.random.default_rng(11)
    R = make_events(f, A, False, rng); R["wk"] = week_of(f, R)
    hit_r, net_r, mae_r, th_r = outcomes(f, R)
    hit_m, net_m, _, _ = outcomes(f, R, mirror=True)
    print("real", len(R), flush=True)
    PL = []
    for r in range(3):
        Pp = make_events(f, A, True, rng); Pp["wk"] = week_of(f, Pp)
        hit_p, net_p, _, _ = outcomes(f, Pp)
        PL.append((Pp, hit_p, net_p)); print("placebo", r, len(Pp), flush=True)
    rows = []
    disc_r = f.ts.to_numpy()[R.i.to_numpy()] < np.datetime64("2019-01-01")
    for h in HNAMES:
        # hit table
        wr = weekly(R, R.wk.to_numpy(), hit_r[h]); wm = weekly(R, R.wk.to_numpy(), hit_m[h])
        wp = pd.concat([weekly(Pp, Pp.wk.to_numpy(), hp[h]) for Pp, hp, _ in PL], axis=1).mean(axis=1)
        mets = {("hit", None): (wr, wm, wp)}
        for s in SNAMES:
            wr2 = weekly(R, R.wk.to_numpy(), net_r[(h, s)]); wm2 = weekly(R, R.wk.to_numpy(), net_m[(h, s)])
            wp2 = pd.concat([weekly(Pp, Pp.wk.to_numpy(), npp[(h, s)]) for Pp, _, npp in PL], axis=1).mean(axis=1)
            mets[("ev", s)] = (wr2, wm2, wp2)
        for (kind, s), (wr_, wm_, wp_) in mets.items():
            df = pd.concat([wr_.rename("r"), wm_.rename("m"), wp_.rename("p")], axis=1).dropna()
            for (an, bk), g in df.groupby(level=[0, 1]):
                if len(g) < 60:
                    continue
                d1 = g.r - g.p; d2 = g.r - g.m
                rows.append(dict(kotva=an, vzdalenost_atr=bk, horizont=h, mereni="P(dosazeni)" if kind == "hit" else "EV cisty b.",
                                 stop_atr="-" if kind == "hit" else (s if s else "bez stopu"), tydnu=len(g),
                                 skutecna=g.r.mean(), placebo=g.p.mean(), zrcadlo=g.m.mean(),
                                 efekt_vs_placebo=d1.mean(), t_vs_placebo=d1.mean() / d1.std() * np.sqrt(len(d1)) if d1.std() > 0 else np.nan,
                                 t_vs_zrcadlo=d2.mean() / d2.std() * np.sqrt(len(d2)) if d2.std() > 0 else np.nan))
    T = pd.DataFrame(rows)
    T.round(4).to_csv(os.path.join(OUT, "D_efekt_kotev_placebo.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    for mer in ("P(dosazeni)", "EV cisty b."):
        x = T[T.mereni == mer]
        print(mer, "konfiguraci", len(x), " |t_placebo|>2:", (x.t_vs_placebo.abs() > 2).mean().round(3), " kladne t>2:", (x.t_vs_placebo > 2).sum(),
              " zaporne:", (x.t_vs_placebo < -2).sum(), " |t_zrcadlo|>2:", (x.t_vs_zrcadlo.abs() > 2).mean().round(3))
    x = T[T.mereni == "P(dosazeni)"]
    print(x.groupby("horizont")[["skutecna", "placebo", "zrcadlo", "efekt_vs_placebo"]].mean().round(4))
    print(x.groupby("kotva")[["skutecna", "placebo", "efekt_vs_placebo", "t_vs_placebo"]].mean().round(4))
    print(x.sort_values("t_vs_placebo", ascending=False).head(12).round(3).to_string())
    print(x.sort_values("t_vs_placebo").head(6).round(3).to_string())


if __name__ == "__main__":
    main()
