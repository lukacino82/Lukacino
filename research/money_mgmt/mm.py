"""Block 5 - money management from game theory (poker / blackjack / casino systems) applied to long ES.

Daily ES futures return = change of the back-adjusted ES close (16:00 ET, includes carry) / previous S&P cash close.
Every rule sets the exposure (leverage) L for the next day from information up to today's close; cost 0.01 % of the
traded notional (about 0.5 point per ES contract); exposure capped at 5x; equity <= 5 % of start = ruin (stop).
Rules: buy & hold 1x / 2x / 3x, Kelly and half Kelly (rolling 1y mean / variance), volatility target 15 %,
martingale (double after a losing week), anti-martingale / Paroli (double after a winning week, max 3 steps),
D'Alembert (+0.5x after a losing week, -0.5x after a win), Fibonacci after losing weeks, drawdown pyramiding
(add +0.5x for every further 5 % / 10 % below the high, back to 1x at a new high), 'card counting' (2x only when the
known small edge is on: close below the weekly VWAP -1 SD or RSI(2) < 10), constant-risk sizing from the weekly
drawdown statistics. History 2010-2026 plus a block bootstrap (20-day blocks, 2000 paths of 16 years).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

DATA = "/tmp/claude-0/data"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
COST = 0.0001
LMAX = 5.0


def daily():
    c = pd.read_parquet(os.path.join(DATA, "bcl_cash.parquet"))
    c = c[c.ts >= "2009-12-01"]
    cc = c[c.ts.dt.time == pd.Timestamp("15:59").time()].set_index(c[c.ts.dt.time == pd.Timestamp("15:59").time()].ts.dt.normalize()).C
    f = pd.read_parquet(os.path.join(DATA, "dv", "frame.parquet"), columns=["ts", "C", "vwap_w", "sd_w"])
    e = f[f.ts.dt.time == pd.Timestamp("15:59").time()].set_index("ts")
    e.index = e.index.normalize()
    d = pd.DataFrame({"cash": cc}).join(e, how="inner")
    d["r"] = d.C.diff() / d.cash.shift()
    d = d.dropna()
    # signals known at the close
    chg = d.cash.diff()
    up = chg.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean(); dn = (-chg.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    d["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d["below_w"] = d.C < d.vwap_w - d.sd_w
    return d[d.index >= "2010-01-01"]


def week_flags(idx):
    """True on the last trading day of each week"""
    w = pd.Series(idx.to_period("W-FRI"), index=idx)
    return (w != w.shift(-1)).to_numpy()


def simulate(r, L):
    """r: daily returns, L: exposure decided at the previous close"""
    eq = np.empty(len(r)); e = 1.0; prev = 0.0; ruined = False
    for i in range(len(r)):
        if ruined:
            eq[i] = e; continue
        l = min(max(L[i], 0.0), LMAX)
        e = e * (1 + l * r[i]) - e * COST * abs(l - prev)
        prev = l
        if e <= 0.05:
            e = 0.05 if e > 0 else 0.0; ruined = True
        eq[i] = e
    return eq


def rules(d):
    """each rule returns the exposure array for every day (decided at the previous close)"""
    r = d.r.to_numpy(); n = len(r)
    wk = week_flags(d.index)
    out = {"buy & hold 1x": np.ones(n), "buy & hold 2x": np.full(n, 2.0), "buy & hold 3x": np.full(n, 3.0)}
    mu = pd.Series(r).rolling(252).mean().shift(1).to_numpy(); var = pd.Series(r).rolling(252).var().shift(1).to_numpy()
    k = np.nan_to_num(mu / var, nan=1.0)
    out["Kelly (plny)"] = np.clip(k, 0, LMAX); out["Kelly polovicni"] = np.clip(k / 2, 0, LMAX)
    vol = pd.Series(r).rolling(20).std().shift(1).to_numpy() * np.sqrt(252)
    out["cilova volatilita 15 %"] = np.clip(np.nan_to_num(0.15 / vol, nan=1.0), 0, LMAX)

    def weekly_progression(update):
        L = np.ones(n); cur = 1.0; state = {"wk_start": 1.0, "step": 0, "fib": [1, 1]}
        eq = 1.0; wstart = 1.0
        for i in range(n):
            L[i] = cur
            eq *= 1 + cur * r[i]
            if wk[i]:
                win = eq >= wstart
                cur = update(cur, win, state)
                wstart = eq
        return L

    def mart(cur, win, s):
        return 1.0 if win else min(cur * 2, LMAX)

    def paroli(cur, win, s):
        if win and s["step"] < 3:
            s["step"] += 1; return min(cur * 2, LMAX)
        s["step"] = 0; return 1.0

    def dalembert(cur, win, s):
        return max(0.5, min(LMAX, cur - 0.5 if win else cur + 0.5))

    def fibo(cur, win, s):
        f = s["fib"]
        if win:
            s["fib"] = [1, 1]; return 1.0
        f.append(f[-1] + f[-2]); return min(float(f[-1]), LMAX)

    out["martingale (2x po ztratovem tydnu)"] = weekly_progression(mart)
    out["anti-martingale / Paroli (2x po ziskovem tydnu, max 3)"] = weekly_progression(paroli)
    out["D'Alembert (+0.5x po ztrate, -0.5x po zisku)"] = weekly_progression(dalembert)
    out["Fibonacci po ztratovych tydnech"] = weekly_progression(fibo)
    px = d.cash.to_numpy()
    for step in (0.05, 0.10):
        L = np.ones(n); hi = px[0]
        for i in range(1, n):
            hi = max(hi, px[i - 1])
            dd = 1 - px[i - 1] / hi
            L[i] = 1 + 0.5 * np.floor(dd / step)
        out[f"pyramidovani: +0.5x za kazdych {int(step * 100)} % pod maximem"] = np.clip(L, 0, LMAX)
    sig = (d.rsi2.to_numpy() < 10) | d.below_w.to_numpy()
    out["pocitani karet: 2x pri signalu (RSI2<10 nebo pod W-VWAP -1SD)"] = np.r_[1.0, np.where(sig[:-1], 2.0, 1.0)]
    # constant risk from weekly drawdown statistics: leverage so that the 99th percentile weekly drop of the
    # previous 52 weeks costs 10 % of the account
    wd = pd.Series(r).rolling(5).sum().rolling(260).quantile(0.01).shift(1).to_numpy()
    out["riziko z tydennich propadu (q99 tydne = 10 % uctu)"] = np.clip(np.nan_to_num(0.10 / np.abs(wd), nan=1.0), 0, LMAX)
    return out


def metrics(eq, r_bh, idx):
    ret = np.diff(np.r_[1.0, eq]) / np.r_[1.0, eq[:-1]]
    yrs = len(eq) / 252
    dd = eq / np.maximum.accumulate(eq) - 1
    yr = pd.Series(eq, index=idx).groupby(idx.year).last()
    yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] - 1
    X = np.c_[np.ones(len(ret)), r_bh]
    b, *_ = np.linalg.lstsq(X, ret, rcond=None)
    res = ret - X @ b
    return dict(CAGR=eq[-1] ** (1 / yrs) - 1 if eq[-1] > 0 else -1, konec_x=eq[-1], maxDD=dd.min(),
                Sharpe=ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else np.nan,
                nejhorsi_rok=yret.min(), ztratovych_let=int((yret < 0).sum()),
                alfa_rok=b[0] * 252, alfa_t=b[0] / np.sqrt(res.var() / len(ret)), beta=b[1],
                prum_expozice=np.nan, ruin=eq[-1] <= 0.05)


def bootstrap(r, rulefun_d, d, paths=2000, block=20, seed=7):
    """block bootstrap of the daily return series; rules recomputed on every synthetic path"""
    rng = np.random.default_rng(seed)
    n = len(r); nb = n // block
    res = {}
    for p in range(paths):
        starts = rng.integers(0, n - block, nb)
        ii = (starts[:, None] + np.arange(block)).ravel()
        dd = d.iloc[ii].copy()
        dd.index = d.index[:len(ii)]
        dd["cash"] = np.cumprod(1 + dd.r.to_numpy()) * 1000
        for name, L in rulefun_d(dd).items():
            eq = simulate(dd.r.to_numpy(), L)
            yrs = len(eq) / 252
            res.setdefault(name, []).append((eq[-1] ** (1 / yrs) - 1 if eq[-1] > 0 else -1,
                                             (eq / np.maximum.accumulate(eq) - 1).min(), eq[-1] <= 0.05))
    rows = []
    for name, v in res.items():
        a = np.array(v)
        rows.append(dict(pravidlo=name, CAGR_median=np.median(a[:, 0]), CAGR_p5=np.quantile(a[:, 0], 0.05),
                         maxDD_median=np.median(a[:, 1]), p_DD_horsi_50pct=(a[:, 1] < -0.5).mean(),
                         p_ruin=a[:, 2].mean()))
    return pd.DataFrame(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    d = daily()
    r = d.r.to_numpy()
    R = rules(d)
    rows = []; eqs = {}
    for name, L in R.items():
        eq = simulate(r, L); eqs[name] = eq
        m = metrics(eq, r, d.index); m["prum_expozice"] = np.clip(L, 0, LMAX).mean(); m["max_expozice"] = np.clip(L, 0, LMAX).max()
        lev = np.clip(L, 0, LMAX).mean()
        eqb = simulate(r, np.full(len(r), lev)); mb = metrics(eqb, r, d.index)
        m.update(BH_stejna_expozice_CAGR=mb["CAGR"], BH_stejna_expozice_maxDD=mb["maxDD"],
                 BH_stejna_expozice_Sharpe=mb["Sharpe"])
        for lab, sel in (("2010_18", d.index < "2019-01-01"), ("2019_26", d.index >= "2019-01-01")):
            rr = r[sel]; e2 = simulate(rr, L[sel]); m2 = metrics(e2, rr, d.index[sel])
            m[f"alfa_t_{lab}"] = m2["alfa_t"]; m[f"Sharpe_{lab}"] = m2["Sharpe"]
        rows.append(dict(pravidlo=name, **m))
    H = pd.DataFrame(rows)
    H.round(4).to_csv(os.path.join(OUT, "A_historie_2010_2026.csv"), index=False)
    pd.DataFrame(eqs, index=d.index).to_parquet(os.path.join(OUT, "equity.parquet"))
    pd.set_option("display.width", 250)
    print(H.round(3).to_string(), flush=True)
    B = bootstrap(r, rules, d, paths=int(os.environ.get("PATHS", 2000)))
    B.round(4).to_csv(os.path.join(OUT, "B_bootstrap.csv"), index=False)
    print(B.round(3).to_string())


if __name__ == "__main__":
    main()
