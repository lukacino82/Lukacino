"""RRR matrix analysis (reads the engine output in /tmp/claude-0/data/rrr).

A  grand table: every horizon x side x SL x RRR - win rate vs breakeven (incl. cost), expectancy in R and points,
   t (day-clustered), discovery 2011-18 vs test 2019-26, and win rate vs the driftless random-walk value 1/(1+RRR).
B  time windows: best hour / weekday / month chosen on 2011-18 for every combination -> result in 2019-26.
C  losing streaks: one position at a time (next hourly entry after the exit), streak frequencies vs an iid
   sequence with the same win rate.
D  minimum winners per 10 / 100 / 1000 trades for every SL x RRR (cost 0.5 point per round turn).
E  alpha vs buy & hold for the best combination per horizon/side picked on 2011-18, traded 2019-26
   (risk 1 % of equity per trade, one position at a time).
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
SPLIT = pd.Timestamp("2019-01-01")


def load(mode, h, side):
    z = np.load(os.path.join(E.CACHE, f"{mode}_{h}_{side}.npz"))
    return {k: z[k] for k in z.files}


def outcomes(z, i_sl, r):
    """R per trade (after cost), exit offset (bars), win flag, for SL index i_sl and RRR r"""
    s = z["slv"][i_sl]
    j = np.searchsorted(z["tpv"], np.round(s * r, 4))
    tsl = z["t_sl"][:, i_sl].astype(np.int64); ttp = z["t_tp"][:, j].astype(np.int64)
    big = 1 << 40
    a = np.where(tsl >= 0, tsl, big); b = np.where(ttp >= 0, ttp, big)
    win = b < a
    loss = (a <= b) & (a < big)
    opn = ~win & ~loss
    cost_r = COST / (s * z["scale"])
    R = np.where(win, r, np.where(loss, -1.0, z["cl"] / s)) - cost_r
    hold = z["end"] - z["ent"]
    ex = np.where(win, b, np.where(loss, a, hold))
    return R, ex, win, loss, opn


def meta(bars, ent):
    ts = bars.ts.iloc[ent].reset_index(drop=True)
    return pd.DataFrame({"ts": ts, "gday": bars.gday.iloc[ent].to_numpy(), "hour": ts.dt.hour.to_numpy(),
                         "wd": bars.gday.iloc[ent].dt.day_of_week.to_numpy(), "month": ts.dt.month.to_numpy()})


def clustered_t(R, day):
    s = pd.Series(R).groupby(day).mean()
    return s.mean() / s.std() * np.sqrt(len(s)) if len(s) > 2 else np.nan


@njit(cache=True)
def streaks(win_seq):
    """lengths of losing streaks in a sequence of trades (True = win)"""
    out = np.zeros(len(win_seq) + 1, np.int64); m = 0; c = 0
    for w in win_seq:
        if w:
            if c:
                out[m] = c; m += 1
            c = 0
        else:
            c += 1
    if c:
        out[m] = c; m += 1
    return out[:m]


@njit(cache=True)
def sequence(ent, ex, order_ok):
    """one position at a time: indices of trades taken (entries sorted by time)"""
    take = np.empty(len(ent), np.int64); m = 0; free = -1
    for k in range(len(ent)):
        if not order_ok[k]:
            continue
        if ent[k] > free:
            take[m] = k; m += 1; free = ent[k] + ex[k]
    return take[:m]


@njit(cache=True)
def iid_streak_freq(p_win, n, k, sims=200, seed=1):
    np.random.seed(seed); cnt = 0.0; mx = 0.0
    for _ in range(sims):
        s = streaks(np.random.random(n) < p_win)
        cnt += (s >= k).sum()
        mx += s.max() if len(s) else 0
    return cnt / sims, mx / sims


def main():
    os.makedirs(OUT, exist_ok=True)
    bars = E.load_bars()[["ts", "gday", "Close"]]
    rows, sel, streak_rows, alpha_rows = [], [], [], []
    daily_close = bars.groupby("gday").Close.last()
    bh = daily_close.pct_change().dropna()
    for mode in ("points", "atr"):
        for h in E.HORIZONS:
            for side in ("long", "short"):
                z = load(mode, h, side)
                M = meta(bars, z["ent"])
                disc = (M.ts < SPLIT).to_numpy()
                best = None
                for i_sl, s in enumerate(z["slv"]):
                    for r in E.RRR:
                        R, ex, win, loss, opn = outcomes(z, i_sl, r)
                        be = (1 + COST / (s * z["scale"])).mean() / (1 + r)
                        row = dict(mode=mode, horizont=h, smer=side, SL=s, RRR=r, n=len(R), win=win.mean(),
                                   open=opn.mean(), breakeven_win=be, nahodna_win=1 / (1 + r), R=R.mean(),
                                   t=clustered_t(R, M.gday.to_numpy()), R_2011_18=R[disc].mean(),
                                   R_2019_26=R[~disc].mean(),
                                   body=(R * s * z["scale"]).mean())
                        rows.append(row)
                        # B: best hour / weekday / month chosen on 2011-18
                        for dim in ("hour", "wd", "month"):
                            g_d = pd.Series(R[disc]).groupby(M[dim].to_numpy()[disc]).agg(["mean", "size"])
                            g_d = g_d[g_d["size"] >= 100]
                            if len(g_d) == 0:
                                continue
                            g_t = pd.Series(R[~disc]).groupby(M[dim].to_numpy()[~disc]).mean()
                            b = g_d["mean"].idxmax()
                            sel.append(dict(mode=mode, horizont=h, smer=side, SL=s, RRR=r, okno=dim, vybrane=b,
                                            R_vyber_2011_18=g_d["mean"].max(), R_vybrane_2019_26=g_t.get(b, np.nan),
                                            R_vsechna_2019_26=R[~disc].mean()))
                        if best is None or row["R_2011_18"] > best[0]:
                            best = (row["R_2011_18"], i_sl, r)
                        # C: streaks for points mode only (one position at a time, every hour eligible)
                        if mode == "points":
                            order = np.argsort(z["ent"], kind="stable")
                            tk = sequence(z["ent"][order], ex[order], np.ones(len(order), bool))
                            w = win[order][tk]
                            sk = streaks(w)
                            yrs = (M.ts.iloc[order[tk[-1]]] - M.ts.iloc[order[tk[0]]]).days / 365.25
                            fr = {}
                            for k in (5, 10, 20, 30, 50):
                                fr[f"serie>={k}"] = int((sk >= k).sum())
                            iid10, iidmax = iid_streak_freq(w.mean(), len(w), 10)
                            streak_rows.append(dict(horizont=h, smer=side, SL=s, RRR=r, obchodu=len(w),
                                                    obchodu_rocne=len(w) / yrs, win=w.mean(), max_serie=sk.max(),
                                                    iid_max_serie=iidmax, **fr, iid_serie10=iid10,
                                                    R_sekvence=R[order][tk].mean()))
                # E: alpha of the best discovery combination, traded in 2019-26
                _, i_sl, r = best
                R, ex, win, loss, opn = outcomes(z, i_sl, r)
                order = np.argsort(z["ent"], kind="stable")
                ok = (M.ts >= SPLIT).to_numpy()[order]
                tk = sequence(z["ent"][order], ex[order], ok)
                idx = order[tk]
                exit_bar = z["ent"][idx] + ex[idx]
                eday = bars.gday.iloc[np.minimum(exit_bar, len(bars) - 1)].to_numpy()
                pr = pd.Series(0.01 * R[idx], index=eday).groupby(level=0).sum()
                b2 = bh.loc[SPLIT:]
                sr = pr.reindex(b2.index).fillna(0)
                X = np.c_[np.ones(len(b2)), b2.to_numpy()]
                coef, *_ = np.linalg.lstsq(X, sr.to_numpy(), rcond=None)
                res = sr.to_numpy() - X @ coef
                se = np.sqrt(res.var(ddof=2) / len(b2))
                eq = (1 + sr).cumprod(); yrs = len(sr) / 252
                beq = (1 + b2).cumprod()
                alpha_rows.append(dict(mode=mode, horizont=h, smer=side, SL=z["slv"][i_sl], RRR=r,
                                       R_vyber_2011_18=best[0], obchodu_2019_26=len(idx), R_2019_26=R[idx].mean(),
                                       CAGR=eq.iloc[-1] ** (1 / yrs) - 1, maxDD=(eq / eq.cummax() - 1).min(),
                                       alfa_rok=coef[0] * 252, alfa_t=coef[0] / se, beta=coef[1],
                                       BH_CAGR=beq.iloc[-1] ** (1 / yrs) - 1))
                print(mode, h, side, "done", flush=True)
    A = pd.DataFrame(rows); A.round(4).to_csv(os.path.join(OUT, "A_grand.csv"), index=False)
    B = pd.DataFrame(sel); B.round(4).to_csv(os.path.join(OUT, "B_time_windows.csv"), index=False)
    C = pd.DataFrame(streak_rows); C.round(4).to_csv(os.path.join(OUT, "C_streaks.csv"), index=False)
    Al = pd.DataFrame(alpha_rows); Al.round(4).to_csv(os.path.join(OUT, "E_alpha.csv"), index=False)
    # D: minimum winners
    drow = []
    for s in E.SL_PTS:
        for r in E.RRR:
            c = COST / s
            w = (1 + c) / (1 + r)
            drow.append(dict(SL=s, RRR=r, TP=s * r, breakeven_win=w, min_vyher_z_10=int(np.ceil(10 * w - 1e-9)),
                             min_vyher_ze_100=int(np.ceil(100 * w - 1e-9)), min_vyher_z_1000=int(np.ceil(1000 * w - 1e-9))))
    D = pd.DataFrame(drow); D.round(4).to_csv(os.path.join(OUT, "D_min_winners.csv"), index=False)
    print("done")


if __name__ == "__main__":
    main()
