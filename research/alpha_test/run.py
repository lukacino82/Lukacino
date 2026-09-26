"""Run every strategy on both ES data sources and write result tables.

Outputs (research/alpha_test/out/):
  summary.csv          one row per strategy with all gates and the verdict
  trades_<src>.csv     every trade (gross points) for every strategy
  grid.csv             TP/SL plateau grid per strategy (ES3000)
  openx.csv            Open +/- X fade/breakout grid (both sources)
  ranges.csv           daily RTH range distribution
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

from engine import PERIODS, period_of, simulate, simulate_limit, stats
from strategies import features, registry

D = "/tmp/claude-0/data/"
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
COST, STRESS = 0.5, 1.0
TSTOP = 120.0
ATR_GRID = [(tp, sl) for tp in (0.25, 0.5, 0.75, 1.0, 1.5) for sl in (0.5, 0.75, 1.0, 1.5)]
PTS_GRID = [(tp, sl) for tp in (8, 12, 16, 24, 32) for sl in (8, 12, 20, 30, 40)]


def load(name):
    S = pickle.load(open(D + name + "_sess.pkl", "rb"))
    return S, features(S)


def exits_for(S, days, kind, tp, sl):
    if kind == "atr":
        a = S.R.atr20.to_numpy()[days]
        return tp * a, sl * a
    return np.full(len(days), float(tp)), np.full(len(days), float(sl))


def first_signals(S, mask):
    has = mask.any(1)
    days = np.where(has)[0]
    js = mask[days].argmax(1)
    ent = S.nxt[days, js]
    ok = (ent >= 0) & np.isfinite(S.R.atr20.to_numpy()[days])
    return days[ok], js[ok], ent[ok]


def run_trades(S, days, ent, kind, tp, sl):
    tpv, slv = exits_for(S, days, kind, tp, sl)
    pnl, code = simulate(S.o, S.h, S.l, S.c, S.mins, ent.astype(np.int64), S.re[days].astype(np.int64),
                         np.ones(len(days), np.int64), tpv, slv, TSTOP)
    return pnl, code


_null_cache = {}


def null_population(S, key, regime_days, kind, tp, sl):
    """Expectancy of a long entered at EVERY eligible bucket of the regime days with the same exits."""
    ck = (key, tuple(regime_days[:5]), len(regime_days), kind, tp, sl)
    if ck in _null_cache:
        return _null_cache[ck]
    days = np.repeat(regime_days, 72)
    js = np.tile(np.arange(72), len(regime_days))
    ent = S.nxt[days, js]
    ok = (ent >= 0) & np.isfinite(S.R.atr20.to_numpy()[days])
    days, ent = days[ok], ent[ok]
    pnl, _ = run_trades(S, days, ent, kind, tp, sl)
    per = period_of(S.dates[days])
    _null_cache[ck] = (pnl, per)
    return pnl, per


def eval_strategy(S, F, name, st, key):
    kind, tp, sl = st["exit"]
    days, js, ent = first_signals(S, st["mask"])
    pnl, code = run_trades(S, days, ent, kind, tp, sl)
    tr = pd.DataFrame({"strategy": name, "date": S.dates[days], "bucket": js,
                       "entry": S.o[ent], "gross": pnl, "exit": code})
    tr["period"] = period_of(S.dates[days])
    # null model: same exits, every bucket of the same regime days
    reg = F[st["regime"]] & F["ma_ok"] if st["regime"] == "bull_day" else F["all_day"]
    rdays = np.where(reg)[0]
    npnl, nper = null_population(S, key, rdays, kind, tp, sl)
    return tr, npnl, nper


def row_stats(tr, npnl, nper):
    r = {}
    net = tr.gross.to_numpy() - COST
    s = stats(net)
    r.update({k: s[k] for k in ("n", "exp", "win", "pf", "net", "maxdd", "t")})
    r["exp_stress"] = (tr.gross - STRESS).mean() if len(tr) else np.nan
    for pname, _, _ in PERIODS:
        m = (tr.period == pname).to_numpy()
        r[f"n|{pname}"] = int(m.sum())
        r[f"exp|{pname}"] = net[m].mean() if m.any() else np.nan
    # edge vs null (gross vs gross, same exits, matched period mix)
    if len(tr) >= 5 and len(npnl):
        mu = np.array([npnl[nper == p].mean() if (nper == p).any() else npnl.mean() for p in tr.period])
        ex = tr.gross.to_numpy() - mu
        r["null_exp"] = mu.mean() - COST
        r["edge"] = ex.mean()
        r["t_edge"] = ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex)))
    else:
        r["null_exp"] = r["edge"] = r["t_edge"] = np.nan
    return r


def grid_and_wf(S, F, name, st):
    kind = st["exit"][0]
    grid = ATR_GRID if kind == "atr" else PTS_GRID
    days, js, ent = first_signals(S, st["mask"])
    per = period_of(S.dates[days])
    years = S.dates[days].year.to_numpy()
    rows, pn = [], {}
    for tp, sl in grid:
        pnl, _ = run_trades(S, days, ent, kind, tp, sl)
        net = pnl - COST
        pn[(tp, sl)] = net
        rr = dict(strategy=name, tp=tp, sl=sl, n=len(net), exp=net.mean() if len(net) else np.nan)
        for p, _, _ in PERIODS[1:]:
            m = per == p
            rr[p] = net[m].mean() if m.any() else np.nan
        rows.append(rr)
    g = pd.DataFrame(rows)
    pos_all = (g[[p for p, _, _ in PERIODS[1:]]] > 0).all(axis=1)
    plateau_all = pos_all.mean()
    plateau = (g.exp > 0).mean()
    # walk-forward: for each year pick the grid point with the best mean over all prior years
    wf = np.full(len(days), np.nan)
    for y in np.unique(years):
        past = years < y
        if past.sum() < 20:
            continue
        best = max(grid, key=lambda k: pn[k][past].mean())
        cur = years == y
        wf[cur] = pn[best][cur]
    wfv = wf[np.isfinite(wf)]
    wf_series = pd.Series(wf, index=S.dates[days]).dropna()
    return g, plateau, plateau_all, (wfv.sum() if len(wfv) else np.nan), (wfv.mean() if len(wfv) else np.nan), wf_series


# ----------------------------------------------------------------- Open +/- X
OPENX_PTS = [10, 15, 20, 40]
OPENX_ATR = [0.2, 0.3, 0.4, 0.6]
OPENX_RR = [(10, 10), (10, 15), (15, 10), (20, 10), (30, 10), (20, 20), (20, 30), (30, 20), (40, 20), (60, 20)]
OPENX_RR_ATR = [(0.2, 0.2), (0.2, 0.3), (0.3, 0.2), (0.4, 0.2), (0.6, 0.2), (0.4, 0.4), (0.4, 0.6), (0.6, 0.4), (0.8, 0.4), (1.2, 0.4)]


def openx_trades(S, X, tp, sl, side, mode, unit):
    """side +1 long / -1 short. mode 'fade': long = buy limit at O-X, short = sell limit at O+X.
    mode 'break': long = buy stop at O+X, short = sell stop at O-X. Exit TP/SL or 16:00."""
    nd = len(S.dates)
    atr = S.R.atr20.to_numpy()
    ok = np.isfinite(atr)
    d = np.where(ok)[0]
    scale = atr[d] if unit == "atr" else np.ones(len(d))
    O = S.dO[d]
    if mode == "fade":
        px = O - side * X * scale
        fd = np.full(len(d), -side, np.int64)
    else:
        px = O + side * X * scale
        fd = np.full(len(d), side, np.int64)
    pnl, filled, code = simulate_limit(S.o, S.h, S.l, S.c, S.rs[d].astype(np.int64), S.re[d].astype(np.int64),
                                       np.full(len(d), side, np.int64), px, tp * scale, sl * scale, fd)
    return pd.DataFrame({"date": S.dates[d][filled], "gross": pnl[filled], "exit": code[filled]}), len(d)


def openx_grid(S, src):
    rows = []
    for unit, Xs, RR in (("pts", OPENX_PTS, OPENX_RR), ("atr", OPENX_ATR, OPENX_RR_ATR)):
        for mode in ("fade", "break"):
            for side in (1, -1):
                for X in Xs:
                    for tp, sl in RR:
                        tr, ndays = openx_trades(S, X, tp, sl, side, mode, unit)
                        net = tr.gross.to_numpy() - COST
                        per = period_of(pd.DatetimeIndex(tr.date))
                        r = dict(src=src, unit=unit, mode=mode, side="long" if side > 0 else "short", X=X, tp=tp, sl=sl,
                                 days=ndays, fill_rate=len(net) / ndays,
                                 tp_rate=(tr.exit == 1).mean(), sl_rate=(tr.exit == -1).mean(),
                                 **{k: v for k, v in stats(net).items()})
                        for p, _, _ in PERIODS:
                            m = per == p
                            r[f"exp|{p}"] = net[m].mean() if m.any() else np.nan
                        rows.append(r)
    return pd.DataFrame(rows)


def ranges(S, src):
    rng = S.dH - S.dL
    ol = S.dO - S.dL
    ho = S.dH - S.dO
    atr = S.R.atr20.to_numpy()
    df = pd.DataFrame({"date": S.dates, "range": rng, "open_low": ol, "high_open": ho, "atr20": atr,
                       "range_atr": rng / atr, "close_open": S.dC - S.dO, "src": src})
    return df


def main():
    summ, all_tr, grids, openx, rng_all, wf_all = [], [], [], [], [], {}
    null_store = {}
    for src in ("es1m", "esvol"):
        S, F = load(src)
        reg = registry(F)
        rng_all.append(ranges(S, src))
        print(src, "strategies", len(reg))
        for name, st in reg.items():
            tr, npnl, nper = eval_strategy(S, F, name, st, src)
            tr["src"] = src
            all_tr.append(tr)
            r = dict(strategy=name, src=src, phase=st["phase"], rule=st["rule"],
                     exit=f"{st['exit'][0]} TP{st['exit'][1]}/SL{st['exit'][2]}")
            r.update(row_stats(tr, npnl, nper))
            if src == "es1m":
                g, plat, plat_all, wf_net, wf_exp, wf_s = grid_and_wf(S, F, name, st)
                grids.append(g)
                r.update(plateau=plat, plateau_all_periods=plat_all, wf_net=wf_net, wf_exp=wf_exp)
                wf_all[name] = wf_s
                null_store[name] = (npnl, nper)
            summ.append(r)
            print(f"  {name:32s} n={r['n']:4d} exp={r['exp']:6.2f} edge={r['edge']:6.2f} t_edge={r['t_edge']:5.2f}")
        openx.append(openx_grid(S, src))
        print(src, "openx done")
    summ = pd.DataFrame(summ)
    summ.to_csv(os.path.join(OUT, "summary_raw.csv"), index=False)
    pd.concat(all_tr).to_csv(os.path.join(OUT, "trades.csv"), index=False)
    pd.concat(grids).to_csv(os.path.join(OUT, "grid.csv"), index=False)
    pd.concat(openx).to_csv(os.path.join(OUT, "openx.csv"), index=False)
    pd.concat(rng_all).to_csv(os.path.join(OUT, "ranges.csv"), index=False)
    pd.DataFrame(wf_all).to_csv(os.path.join(OUT, "walkforward.csv"))


if __name__ == "__main__":
    main()
