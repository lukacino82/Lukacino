"""Money management: what sizing can and cannot do.

1. Break-even win rate and Kelly fraction for every win rate x reward:risk.
2. How many trades it takes to tell a low-win-rate / high-RRR edge from luck.
3. Losing streaks you must expect.
4. Monte Carlo: fixed fractional, Kelly multiples, martingale, anti-martingale on a stream WITH
   an edge and on a stream WITHOUT one (same win rate geometry).
5. Real streams: RSI(2) < 10 next-day trades (documented edge) and a placebo of random days;
   walk-forward Kelly sizing; equity-curve filter ('bench a strategy in drawdown').
6. A-setups: does a stricter filter with a higher historical win rate keep it later?
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
RNG = np.random.default_rng(42)


def tables():
    rr = [0.5, 1, 1.5, 2, 3, 5, 10, 15, 20]
    wr = [0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]
    be = {R: 1 / (1 + R) for R in rr}
    ev, kelly, n2, n3 = {}, {}, {}, {}
    for p in wr:
        for R in rr:
            e = p * R - (1 - p)               # expectancy in R per trade
            sd = (R + 1) * math.sqrt(p * (1 - p))
            ev[(p, R)] = e
            kelly[(p, R)] = max(p - (1 - p) / R, 0)
            n2[(p, R)] = (2 * sd / e) ** 2 if e > 0 else np.inf
            n3[(p, R)] = (3 * sd / e) ** 2 if e > 0 else np.inf
    to_df = lambda d: pd.DataFrame({R: [d[(p, R)] for p in wr] for R in rr}, index=wr)
    streak = {}
    for p in (0.1, 0.2, 0.3, 0.4, 0.5):
        q = 1 - p
        streak[p] = {N: math.log(N * p) / math.log(1 / q) if N * p > 1 else np.nan for N in (100, 500, 1000)}
    return dict(rr=rr, wr=wr, be=be, ev=to_df(ev), kelly=to_df(kelly), n2=to_df(n2), n3=to_df(n3),
                streak=pd.DataFrame(streak))


def simulate(p, R, n_trades, schemes, n_paths=4000):
    """returns dict scheme -> (median final wealth, P(ruin to <10 %), median max DD)."""
    win = RNG.random((n_paths, n_trades)) < p
    out = {}
    for name, f in schemes.items():
        W = np.ones(n_paths)
        peak = np.ones(n_paths)
        mdd = np.zeros(n_paths)
        stake = np.full(n_paths, np.nan)
        streak_l = np.zeros(n_paths)
        streak_w = np.zeros(n_paths)
        for t in range(n_trades):
            risk = f(W, streak_l, streak_w)
            risk = np.minimum(risk, W)                # cannot risk more than the account
            gain = np.where(win[:, t], risk * R, -risk)
            W = np.maximum(W + gain, 0)
            streak_l = np.where(win[:, t], 0, streak_l + 1)
            streak_w = np.where(win[:, t], streak_w + 1, 0)
            peak = np.maximum(peak, W)
            mdd = np.maximum(mdd, 1 - W / peak)
        out[name] = dict(median=float(np.median(W)), mean=float(W.mean()), ruin=float((W < 0.1).mean()),
                         p_profit=float((W > 1).mean()), mdd=float(np.median(mdd)))
    return out


def schemes_for(p, R):
    k = max(p - (1 - p) / R, 0.0)
    base = 0.01
    return {
        "Fixní 1 % účtu": lambda W, L, Wn: 0.01 * W,
        "Fixní 2 % účtu": lambda W, L, Wn: 0.02 * W,
        "½ Kelly": lambda W, L, Wn: 0.5 * k * W,
        "Kelly": lambda W, L, Wn: k * W,
        "2× Kelly": lambda W, L, Wn: 2 * k * W,
        "Martingale (zdvojení po ztrátě)": lambda W, L, Wn: base * W * (2.0 ** np.minimum(L, 10)),
        "Anti-martingale (+50 % po výhře)": lambda W, L, Wn: base * W * (1.5 ** np.minimum(Wn, 4)),
    }


def monte_carlo():
    rows = []
    for p, R, label in ((0.10, 12, "10 % win rate, 12R (edge +0,30R)"), (1 / 13, 12, "7,7 % win rate, 12R (bez edge)"),
                        (0.55, 1, "55 % win rate, 1R (edge +0,10R)"), (0.50, 1, "50 % win rate, 1R (bez edge)")):
        res = simulate(p, R, 500, schemes_for(p, R))
        for k, v in res.items():
            rows.append(dict(setting=label, scheme=k, **{a: round(b, 3) for a, b in v.items()}))
    return pd.DataFrame(rows)


def real_streams():
    """RSI(2)<10 next-day long (documented edge) vs placebo random days; Kelly + equity filter."""
    from data import load
    from hypotheses import _rsi
    D = load()
    T = D.T
    rsi = _rsi(T.C, 2)
    sig = (rsi < 10).shift().fillna(False).to_numpy()
    r = T.ret.fillna(0).to_numpy() - 0.5 / T.C.to_numpy()  # next-day close-to-close, 0.5 pt cost
    edge = pd.Series(np.where(sig, r, np.nan), index=T.index).dropna()
    # placebo: same number of random days per year
    pl = []
    for y, g in edge.groupby(edge.index.year):
        days = T.index[T.index.year == y]
        pick = RNG.choice(len(days), size=len(g), replace=False)
        pl.append(pd.Series(r[np.searchsorted(T.index, days[np.sort(pick)])], index=days[np.sort(pick)]))
    placebo = pd.concat(pl)

    def sized(stream, mode):
        W, out, hist = 1.0, [], []
        for d, x in stream.items():
            if mode == "fixed":
                f = 1.0
            else:  # walk-forward Kelly on % returns: f = mu / sigma^2 (half), capped 0..4 x notional
                if len(hist) < 30:
                    f = 1.0
                else:
                    h = np.array(hist)
                    f = float(np.clip(0.5 * h.mean() / h.var(), 0, 4))
            W *= 1 + f * x
            out.append(W)
            hist.append(x)
        return pd.Series(out, index=stream.index)

    def eq_filter(stream, lookback=20):
        eq = (1 + stream).cumprod()
        ma = eq.rolling(lookback).mean().shift()
        on = (eq.shift() >= ma).fillna(True)
        return stream.where(on, 0.0)

    def stats(s):
        x = s.to_numpy()
        return dict(n=len(x), mean_bps=round(x.mean() * 1e4, 2), win=round((x > 0).mean() * 100, 1),
                    t=round(x.mean() / x.std(ddof=1) * math.sqrt(len(x)), 2))
    out = dict(edge=stats(edge), placebo=stats(placebo))
    curves = {}
    for nm, s in (("RSI(2)<10", edge), ("Placebo", placebo)):
        for mode in ("fixed", "kelly"):
            curves[f"{nm} · {'1× nominál' if mode == 'fixed' else 'walk-forward ½ Kelly'}"] = sized(s, mode)
        f = eq_filter(s)
        curves[f"{nm} · equity filtr (MA20)"] = (1 + f).cumprod()
        out[f"{nm}_filter"] = stats(f[f != 0])
    fin = {k: round(float(v.iloc[-1]), 3) for k, v in curves.items()}
    dd = {k: round(float((v / v.cummax() - 1).min()) * 100, 1) for k, v in curves.items()}
    return out, curves, fin, dd


def a_setups():
    """Regression to the mean of win rate and excess across the factory's hypotheses."""
    R = pd.read_csv(os.path.join(OUT, "factory_results.csv"))
    R = R[(R.n_DISC >= 30) & (R.n_VAL >= 10) & (R.n_TEST >= 10)].copy()
    R["win_LATER"] = (R.win_VAL * R.n_VAL + R.win_TEST * R.n_TEST) / (R.n_VAL + R.n_TEST)
    R["bin"] = pd.qcut(R.win_DISC, 10, duplicates="drop")
    wr = R.groupby("bin", observed=True).agg(win_disc=("win_DISC", "mean"), win_later=("win_LATER", "mean"),
                                             n=("name", "size")).reset_index(drop=True)
    R["tbin"] = pd.cut(R.t_DISC.abs(), [0, 1, 2, 3, 10])
    tt = R.groupby("tbin", observed=True).agg(ex_disc=("ex_DISC", "mean"), ex_later=("ex_LATER", "mean"),
                                              share_pos=("ex_LATER", lambda x: (x > 0).mean()), n=("name", "size")).reset_index()
    tt["tbin"] = tt.tbin.astype(str)
    scatter = R[["t_DISC", "t_LATER", "family"]].dropna().sample(min(1500, len(R)), random_state=1)
    return wr, tt, scatter


def rsi_strictness():
    """Poker 'play only premium hands': stricter RSI(2) thresholds -> win rate, n, CI."""
    from data import load
    from hypotheses import _rsi
    D = load(); T = D.T
    rsi = _rsi(T.C, 2).shift()
    r = (T.ret - 0.5 / T.C).to_numpy()
    rows = []
    for th in (50, 30, 20, 10, 5, 2, 1):
        m = (rsi < th).to_numpy()
        x = r[m & np.isfinite(r)]
        n = len(x)
        mu = x.mean()
        se = x.std(ddof=1) / math.sqrt(n)
        rows.append(dict(threshold=th, n=n, trades_per_year=round(n / 18.4, 1), win=round((x > 0).mean() * 100, 1),
                         mean_bps=round(mu * 1e4, 1), ci_lo=round((mu - 2 * se) * 1e4, 1), ci_hi=round((mu + 2 * se) * 1e4, 1),
                         t=round(mu / se, 2), total_pct=round(x.sum() * 100, 1)))
    return pd.DataFrame(rows)


def main():
    tb = tables()
    mc = monte_carlo()
    real, curves, fin, dd = real_streams()
    wr, tt, sc = a_setups()
    rs = rsi_strictness()
    pd.set_option("display.width", 250)
    print("break-even WR", {k: round(v, 3) for k, v in tb["be"].items()})
    print("EV (R)\n", tb["ev"].round(2)); print("Kelly\n", tb["kelly"].round(3)); print("n for t=2\n", tb["n2"].round(0))
    print("expected longest losing streak\n", tb["streak"].round(1))
    print(mc.to_string())
    print(real); print(fin); print(dd)
    print(wr.round(3)); print(tt.round(2)); print(rs.to_string())
    pickle_out = dict(tables={k: (v.to_dict() if isinstance(v, pd.DataFrame) else v) for k, v in tb.items()},
                      mc=mc, real=real, fin=fin, dd=dd, wr=wr, tt=tt, scatter=sc, rsi=rs,
                      curves={k: v.resample("W-FRI").last().dropna() for k, v in curves.items()})
    import pickle
    pickle.dump(pickle_out, open(os.path.join(OUT, "money.pkl"), "wb"))


if __name__ == "__main__":
    main()
