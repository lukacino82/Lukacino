"""RRR matrix part 2 (2011-2026, cost 0.5 point per round turn):

F  stop-hunt hypothesis ("algos first push price into retail stops, then the real move"): during RTH price breaks the
   prior day's low (or the overnight low) by >= 1 point and closes back above it within 30 minutes -> long at the
   next bar; mirror for shorts at the prior day's high / overnight high. Variants: cumulative delta during the sweep
   > 0 (buyers absorbing) or <= 0; with / without the daily bias filter (close vs 200-day average).
   SL fixed 6..100 points x RRR 1..25, plus the structural stop (sweep extreme - 1 point). Benchmark: an entry at a
   random RTH minute of the same day with the same SL/TP (5 draws per event).
G  probe position: hourly entries; the real position is opened only after a probe confirmed the move
   (+q x SL in favour before -SL, stop order) or, the averaging-down variant, after a move of -q x SL (limit order);
   same SL/TP measured from the real entry. Compared with the direct entry at the hour.
H  machine learning, walk-forward: LightGBM classifiers per SL x RRR on 18 features known at the entry (hour, weekday,
   ATRs, returns, distance to prior day high/low, overnight range, delta, trend, RSI2, volatility regime); trained on
   all years before Y, applied to year Y (2015..2026); trade only when p(win) > breakeven + 0.03.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
COST = 0.5


@njit(cache=True)
def outcome_one(O, H, L, C, i0, p, i1, side, sl, tp):
    """R (before cost) and exit bar for one trade entered at price p at bar i0 (bar i0 included, conservative)"""
    for t in range(i0, i1 + 1):
        if side == 1:
            a = p - L[t]; f = H[t] - p
        else:
            a = H[t] - p; f = p - L[t]
        if a >= sl:
            return -1.0, t
        if f >= tp:
            return tp / sl, t
    return (C[i1] - p) * side / sl, i1


@njit(cache=True)
def grid_outcomes(O, H, L, C, ent, price, end, side, SL, RR):
    n = len(ent); out = np.zeros((n, len(SL), len(RR)))
    for e in range(n):
        for a in range(len(SL)):
            for b in range(len(RR)):
                out[e, a, b] = outcome_one(O, H, L, C, ent[e], price[e], end[e], side, SL[a], SL[a] * RR[b])[0]
    return out


@njit(cache=True)
def sweep_events(H, L, C, delta, minute_of_day, gpos, lvl_lo, lvl_hi, window):
    """RTH (9:30-15:59) sweeps of a level by >= 1 point with a close back inside within `window` minutes.
    Returns entry bar (next bar), side, sweep extreme, delta during the sweep, level type (0 low, 1 high)."""
    n = len(C)
    ent = np.empty(200000, np.int64); sd = np.empty(200000, np.int64); ext = np.empty(200000); dl = np.empty(200000)
    m = 0
    cur = -1; used_lo = False; used_hi = False; br_lo = -1; br_hi = -1; ex_lo = 0.0; ex_hi = 0.0
    for t in range(1, n - 1):
        if gpos[t] != cur:
            cur = gpos[t]; used_lo = False; used_hi = False; br_lo = -1; br_hi = -1
        md = minute_of_day[t]
        if md < 570 or md > 959:
            continue
        lo = lvl_lo[t]; hi = lvl_hi[t]
        if not used_lo and np.isfinite(lo):
            if br_lo < 0 and L[t] <= lo - 1:
                br_lo = t; ex_lo = L[t]
            if br_lo >= 0:
                ex_lo = min(ex_lo, L[t])
                if C[t] > lo and t > br_lo:
                    d = 0.0
                    for k in range(br_lo, t + 1):
                        d += delta[k]
                    ent[m] = t + 1; sd[m] = 1; ext[m] = ex_lo; dl[m] = d; m += 1; used_lo = True
                elif t - br_lo > window:
                    used_lo = True
        if not used_hi and np.isfinite(hi):
            if br_hi < 0 and H[t] >= hi + 1:
                br_hi = t; ex_hi = H[t]
            if br_hi >= 0:
                ex_hi = max(ex_hi, H[t])
                if C[t] < hi and t > br_hi:
                    d = 0.0
                    for k in range(br_hi, t + 1):
                        d += delta[k]
                    ent[m] = t + 1; sd[m] = -1; ext[m] = ex_hi; dl[m] = d; m += 1; used_hi = True
                elif t - br_hi > window:
                    used_hi = True
    return ent[:m], sd[:m], ext[:m], dl[:m]


@njit(cache=True)
def probe_entries(O, H, L, ent, end, side, sl, q):
    """confirmation (q > 0, stop order at +q*sl before -sl) or averaging down (q < 0, limit at q*sl):
    returns trigger bar and price (-1 if never)"""
    n = len(ent); tb = -np.ones(n, np.int64); tp_ = np.zeros(n)
    for e in range(n):
        p0 = O[ent[e]]; trig = p0 + side * q * sl
        for t in range(ent[e], end[e] + 1):
            if q > 0:
                adv = (p0 - L[t]) if side == 1 else (H[t] - p0)
                hit = (H[t] >= trig) if side == 1 else (L[t] <= trig)
                if adv >= sl:
                    break
                if hit:
                    tb[e] = t; tp_[e] = trig; break
            else:
                hit = (L[t] <= trig) if side == 1 else (H[t] >= trig)
                if hit:
                    tb[e] = t; tp_[e] = trig; break
    return tb, tp_


def daily_frame(d):
    g = d.groupby("gday").agg(H=("High", "max"), L=("Low", "min"), C=("Close", "last"))
    tr = np.maximum(g.H - g.L, np.maximum((g.H - g.C.shift()).abs(), (g.L - g.C.shift()).abs()))
    g["atr"] = tr.rolling(14).mean()
    g["sma200"] = g.C.rolling(200).mean()
    g["sma50"] = g.C.rolling(50).mean()
    ch = g.C.diff()
    up = ch.clip(lower=0).rolling(2).mean(); dn = (-ch.clip(upper=0)).rolling(2).mean()
    g["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    g["ret5"] = g.C.diff(5)
    g["atr_reg"] = g.atr / g.atr.rolling(100).mean()
    return g


def part_F(d, O, H, L, C, gday_pos, days, g):
    md = (d.ts.dt.hour * 60 + d.ts.dt.minute).to_numpy()
    prev = g.shift(1)
    pdl = prev.L.reindex(d.gday).to_numpy(); pdh = prev.H.reindex(d.gday).to_numpy()
    # overnight low/high: 18:00 .. 09:29 of the current Globex day, known from 09:30 on
    onmask = md < 570
    on = d[onmask | (md >= 1080)].groupby("gday").agg(onl=("Low", "min"), onh=("High", "max"))
    onl = on.onl.reindex(d.gday).to_numpy(); onh = on.onh.reindex(d.gday).to_numpy()
    delta = d.delta.to_numpy(float)
    last_bar = pd.Series(np.arange(len(d))).groupby(gday_pos).max().to_numpy()
    trend_up = (prev.C > prev.sma200).reindex(d.gday).to_numpy()
    rows = []
    rng = np.random.default_rng(5)
    SL = E.SL_PTS; RR = E.RRR
    rth_idx_by_day = pd.Series(np.arange(len(d)))[(md >= 570) & (md <= 959)].groupby(gday_pos[(md >= 570) & (md <= 959)]).apply(np.array)
    for lvl_name, lo, hi in (("předchozí den low/high", pdl, pdh), ("overnight low/high", onl, onh)):
        ent, sd, ext, dl = sweep_events(H, L, C, delta, md, gday_pos, lo, hi, 30)
        ok = (d.ts.iloc[ent] >= E.START).to_numpy() & (ent < len(d))
        ent, sd, ext, dl = ent[ok], sd[ok], ext[ok], dl[ok]
        end = last_bar[gday_pos[ent]]
        price = O[ent]
        # null: random RTH minute of the same day (5 draws), same side
        nul_e, nul_s, nul_p = [], [], []
        for k in range(len(ent)):
            cand = rth_idx_by_day.get(gday_pos[ent[k]])
            if cand is None or len(cand) == 0:
                continue
            for _ in range(5):
                j = cand[rng.integers(len(cand))]
                nul_e.append(j); nul_s.append(sd[k])
        nul_e = np.array(nul_e); nul_s = np.array(nul_s)
        for side in (1, -1):
            m = sd == side
            out = grid_outcomes(O, H, L, C, ent[m], price[m], end[m], side, SL, RR)
            mn = nul_s == side
            outn = grid_outcomes(O, H, L, C, nul_e[mn], O[nul_e[mn]], last_bar[gday_pos[nul_e[mn]]], side, SL, RR)
            dpos = dl[m] * side > 0
            bias = trend_up[ent[m]] if side == 1 else ~trend_up[ent[m]]
            bias = np.where(np.isnan(bias.astype(float)), False, bias).astype(bool)
            yrs = d.ts.iloc[ent[m]].dt.year.to_numpy()
            for a, s in enumerate(SL):
                for b, r in enumerate(RR):
                    Rv = out[:, a, b] - COST / s
                    Rn = outn[:, a, b] - COST / s
                    for var, msk in (("vše", np.ones(len(Rv), bool)), ("delta ve směru", dpos), ("delta proti", ~dpos),
                                     ("bias trend", bias), ("bias + delta", bias & dpos)):
                        if msk.sum() < 20:
                            continue
                        x = Rv[msk]
                        rows.append(dict(level=lvl_name, smer="long" if side == 1 else "short", varianta=var,
                                         SL=s, RRR=r, n=int(msk.sum()), win=(x > 0).mean(), R=x.mean(),
                                         t=x.mean() / x.std() * np.sqrt(len(x)), R_nahodny_vstup=Rn.mean(),
                                         R_2011_18=x[yrs[msk] < 2019].mean(), R_2019_26=x[yrs[msk] >= 2019].mean()))
            # structural stop: sweep extreme -/+ 1 point
            sls = np.abs(price[m] - ext[m]) + 1
            for r in RR:
                Rs = np.array([outcome_one(O, H, L, C, ent[m][k], price[m][k], end[m][k], side, sls[k], sls[k] * r)[0]
                               for k in range(m.sum())]) - COST / sls
                for var, msk in (("vše", np.ones(len(Rs), bool)), ("delta ve směru", dpos), ("bias + delta", bias & dpos)):
                    x = Rs[msk]
                    rows.append(dict(level=lvl_name, smer="long" if side == 1 else "short", varianta=var + " (SL za extrém)",
                                     SL=float(np.median(sls[msk])), RRR=r, n=int(msk.sum()), win=(x > 0).mean(), R=x.mean(),
                                     t=x.mean() / x.std() * np.sqrt(len(x)), R_nahodny_vstup=np.nan,
                                     R_2011_18=x[yrs[msk] < 2019].mean(), R_2019_26=x[yrs[msk] >= 2019].mean()))
        print("F", lvl_name, len(ent), flush=True)
    return pd.DataFrame(rows)


def part_G(O, H, L, C):
    rows = []
    for h in ("intraday", "5D"):
        z = np.load(os.path.join(E.CACHE, f"points_{h}_long.npz"))
        ent, end = z["ent"], z["end"]
        for s in (10, 20, 40):
            for r in (1.5, 3, 10):
                base = grid_outcomes(O, H, L, C, ent, O[ent], end, 1, np.array([float(s)]), np.array([float(r)]))[:, 0, 0] - COST / s
                rows.append(dict(horizont=h, SL=s, RRR=r, varianta="přímý vstup v celou hodinu", n=len(base),
                                 podil_aktivovanych=1.0, R=base.mean(), R_na_signal=base.mean()))
                for q in (0.25, 0.5, -0.25, -0.5):
                    tb, tp_ = probe_entries(O, H, L, ent, end, 1, float(s), q)
                    ok = tb >= 0
                    Rr = grid_outcomes(O, H, L, C, tb[ok], tp_[ok], end[ok], 1, np.array([float(s)]), np.array([float(r)]))[:, 0, 0] - COST / s
                    name = (f"sonda: reálná pozice až po +{q} SL (stop)" if q > 0 else f"průměrování dolů: reálná pozice na {q} SL (limit)")
                    rows.append(dict(horizont=h, SL=s, RRR=r, varianta=name, n=int(ok.sum()), podil_aktivovanych=ok.mean(),
                                     R=Rr.mean(), R_na_signal=Rr.sum() / len(ent)))
        print("G", h, flush=True)
    return pd.DataFrame(rows)


def features(d, ent, g):
    ts = d.ts.iloc[ent]
    gd = d.gday.iloc[ent]
    prev = g.shift(1)
    P = prev.reindex(gd)
    c = d.Close.to_numpy(); o = d.Open.to_numpy()
    cs_c = pd.Series(c)
    p0 = o[ent]
    lag60 = cs_c.shift(1).to_numpy()[ent] - cs_c.shift(61).to_numpy()[ent]
    dsum = pd.Series(d.delta.to_numpy(float)).rolling(60).sum().shift(1).to_numpy()[ent]
    vsum = pd.Series(d.Volume.to_numpy(float)).rolling(60).sum().shift(1).to_numpy()[ent]
    gstart = d.groupby("gday").Open.first().reindex(gd).to_numpy()
    cumd = d.groupby("gday").delta.cumsum().shift(1).to_numpy()[ent]
    cumv = d.groupby("gday").Volume.cumsum().shift(1).to_numpy()[ent]
    atr = P.atr.to_numpy()
    X = pd.DataFrame({
        "hour": ts.dt.hour.to_numpy(), "wd": gd.dt.day_of_week.to_numpy(), "atr": atr,
        "atr_reg": P.atr_reg.to_numpy(), "ret60": lag60 / atr, "ret_gday": (p0 - gstart) / atr,
        "ret_prev": (P.C - prev.shift(1).C.reindex(gd)).to_numpy() / atr, "d_pdl": (p0 - P.L.to_numpy()) / atr,
        "d_pdh": (P.H.to_numpy() - p0) / atr, "range_prev": (P.H - P.L).to_numpy() / atr,
        "delta60": dsum / np.maximum(vsum, 1), "cumdelta": cumd / np.maximum(cumv, 1),
        "trend200": (P.C / P.sma200 - 1).to_numpy(), "trend50": (P.C / P.sma50 - 1).to_numpy(),
        "rsi2": P.rsi2.to_numpy(), "ret5": P.ret5.to_numpy() / atr, "month": ts.dt.month.to_numpy(),
        "minute_rth": ((ts.dt.hour * 60 + ts.dt.minute) >= 570).to_numpy().astype(int)})
    return X


def part_H(d, g):
    import lightgbm as lgb
    rows = []
    for h in ("intraday", "5D"):
        for side in ("long", "short"):
            z = np.load(os.path.join(E.CACHE, f"points_{h}_{side}.npz"))
            ent = z["ent"]
            X = features(d, ent, g)
            yr = d.ts.iloc[ent].dt.year.to_numpy()
            for i_sl, s in enumerate(z["slv"]):
                if s not in (10, 20, 40):
                    continue
                for r in (1.5, 3, 10):
                    j = np.searchsorted(z["tpv"], np.round(s * r, 4))
                    tsl = z["t_sl"][:, i_sl].astype(np.int64); ttp = z["t_tp"][:, j].astype(np.int64)
                    big = 1 << 40
                    a = np.where(tsl >= 0, tsl, big); b = np.where(ttp >= 0, ttp, big)
                    win = b < a; loss = (a <= b) & (a < big)
                    R = np.where(win, r, np.where(loss, -1.0, z["cl"] / s)) - COST / s
                    y = win.astype(int)
                    be = (1 + COST / s) / (1 + r)
                    for Y in range(2015, 2027):
                        tr = yr < Y; te = yr == Y
                        if te.sum() == 0:
                            continue
                        m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200,
                                               subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
                        m.fit(X[tr], y[tr])
                        p = m.predict_proba(X[te])[:, 1]
                        pick = p > be + 0.03
                        rows.append(dict(horizont=h, smer=side, SL=s, RRR=r, rok=Y, n_vse=int(te.sum()),
                                         R_vse=R[te].mean(), n_vybrane=int(pick.sum()),
                                         R_vybrane=R[te][pick].mean() if pick.any() else np.nan,
                                         auc=_auc(y[te], p)))
            print("H", h, side, flush=True)
    return pd.DataFrame(rows)


def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return roc_auc_score(y, p) if 0 < y.sum() < len(y) else np.nan


def main():
    os.makedirs(OUT, exist_ok=True)
    d = E.load_bars()
    O, H, L, C = (d[c].to_numpy(float) for c in ("Open", "High", "Low", "Close"))
    days = np.unique(d.gday.to_numpy()); gday_pos = np.searchsorted(days, d.gday.to_numpy())
    g = daily_frame(d)
    which = sys.argv[1] if len(sys.argv) > 1 else "FGH"
    if "F" in which:
        part_F(d, O, H, L, C, gday_pos, days, g).round(4).to_csv(os.path.join(OUT, "F_stophunt.csv"), index=False)
    if "G" in which:
        part_G(O, H, L, C).round(4).to_csv(os.path.join(OUT, "G_probe.csv"), index=False)
    if "H" in which:
        part_H(d, g).round(4).to_csv(os.path.join(OUT, "H_ml.csv"), index=False)


if __name__ == "__main__":
    main()
