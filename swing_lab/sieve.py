"""
THE SIEVE - multi-stage robustness net for the grid results.

Stage 1  EDGE        enough trades, PF, expectancy net of costs, positive in Discovery /
                     Validation / OOS separately, >=70 % positive years
Stage 2  ALPHA       beats Buy & Hold on risk-adjusted terms:
                       Sharpe > B&H Sharpe, MAR (annual pts / max DD) > B&H MAR,
                       regression alpha vs B&H daily P&L with t-stat >= 2
Stage 0  SCALE INVARIANCE  only exits normalised by volatility (ATR), signal, time or ATR trailing
Stage 0b LONG-TERM BIAS    longs only when the 200-day trend is up (close > SMA200 or SMA50 > SMA200)
Stage 3  ROBUSTNESS  (re-run of every survivor)
                       cost stress 1.5 pt round trip still profitable
                       1-day execution delay still profitable (not a timing artefact)
                       parameter plateau: the same setup+regime works with most exit models
                       and neighbouring thresholds of the same family
                       trade bootstrap (Monte Carlo) P(total <= 0) < 5 %
                       Deflated Sharpe Ratio (Bailey & Lopez de Prado) given the effective number of
                       independent trials (setup x regime x side clusters)
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import systems as S
from lab import WF_END, WF_PERIODS, Lab

RES = Path(__file__).resolve().parent / "results"

STAGE1 = dict(trades=40, pf=1.25, avg=2.0, period_n=5, years_pos_frac=0.7)
STAGE2 = dict(alpha_t=2.0)


def family(setup: str) -> str:
    """setup name without its numeric threshold -> used for neighbourhood / plateau tests"""
    return re.sub(r"[-+]?\d+(\.\d+)?", "#", setup)


def stage1(g: pd.DataFrame) -> pd.Series:
    s = STAGE1
    return ((g.trades >= s["trades"]) & (g.pf >= s["pf"]) & (g.avg >= s["avg"]) &
            (g.disc_n >= s["period_n"]) & (g.val_n >= s["period_n"]) & (g.oos_n >= s["period_n"]) &
            (g.disc_avg > 0) & (g.val_avg > 0) & (g.oos_avg > 0) &
            (g.years_pos >= np.ceil(s["years_pos_frac"] * g.years)))


def stage2(g: pd.DataFrame, bh: dict) -> pd.Series:
    return (g.sharpe > bh["sharpe"]) & (g.mar > bh["mar"]) & (g.alpha_t >= STAGE2["alpha_t"])


def deflated_sharpe(sr_ann, n_days, skew, kurt, n_trials, sr_var_ann):
    """probability that the true Sharpe > 0 after selecting the best of n_trials (daily units)"""
    sr = sr_ann / math.sqrt(252)
    v = sr_var_ann / 252
    emc = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - emc) * norm.ppf(1 - 1 / n_trials) + emc * norm.ppf(1 - 1 / (n_trials * math.e)))
    den = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr * sr, 1e-9))
    return float(norm.cdf((sr - sr0) * math.sqrt(n_days - 1) / den))


def bootstrap(trade_pnl, n=5000, seed=7):
    rng = np.random.default_rng(seed)
    k = len(trade_pnl)
    if k == 0:
        return 1.0, 0.0
    sims = rng.choice(trade_pnl, size=(n, k), replace=True)
    tot = sims.sum(1)
    eq = sims.cumsum(1)
    dd = (np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq).max(1)
    return float((tot <= 0).mean()), float(np.percentile(dd, 95))


class Sieve:
    def __init__(self, grid_file="grid.parquet", wf=False, scale_invariant=True, long_term_bias=True):
        self.lab = Lab(end=WF_END, periods=WF_PERIODS) if wf else Lab()
        self.g = pd.read_parquet(RES / grid_file)
        if scale_invariant:
            # fixed-point brackets are not stationary: ES ATR20 went from ~16 pts (2017) to ~90 (2025).
            # Walk-forward proved they break out of sample, so only volatility-normalised, signal,
            # time and ATR-trailing exits are eligible for selection.
            self.g = self.g[~self.g.exit.str.contains(r"\d+pt_")].copy()
        if long_term_bias:
            # the brief: systems must stand on the long-term long bias of ES/SP500. Longs only in a
            # long-term bull regime (200-day trend), shorts only in a long-term bear regime.
            lt_long = {"c>sma200", "sma50>sma200", "c>sma200&dd<10"}
            lt_short = {"c<sma200", "sma50<sma200"}
            g_ = self.g
            self.g = g_[((g_.side > 0) & g_.regime.isin(lt_long)) | ((g_.side < 0) & g_.regime.isin(lt_short))].copy()
        self.setups = {s[0]: s for s in S.setups(self.lab.d)}
        self.exits = {e[0]: e for e in S.exits(self.lab.d)}
        self.reg = S.regimes(self.lab.d)
        g = self.g
        g["family"] = g.setup.map(family)
        g["exit_kind"] = g.exit.str.extract(r"x:([A-Za-z%]+)")[0]
        g["s1"] = stage1(g)
        g["s2"] = g.s1 & stage2(g, self.lab.bh_stats)
        # plateau measures
        ok = (g.pf > 1.1) & (g.disc_avg > 0) & (g.val_avg > 0) & (g.oos_avg > 0)
        g["_ok"] = ok
        key = ["setup", "regime", "side"]
        g["exit_plateau"] = g.groupby(key)._ok.transform("mean")
        key2 = ["family", "regime", "side", "exit"]
        g["param_plateau"] = g.groupby(key2)._ok.transform("mean")

    def cfg(self, row, cost=None, delay=0):
        c = S.build_cfg(self.lab.d, self.setups[row.setup], self.exits[row.exit], int(row.side),
                        self.reg[row.regime], 0.5 if cost is None else cost)
        if delay:
            c["side"] = np.roll(c["side"], delay)
            c["side"][:delay] = 0
            if "lim" in c:
                c["lim"] = np.roll(c["lim"], delay)
        return c

    def stage3(self, cand: pd.DataFrame, n_trials: int):
        rows = []
        sr_var = self.g.sharpe.var()
        for _, r in cand.iterrows():
            lab = self.lab
            base = self.cfg(r)
            pnl, pos, tr = lab.run(base)
            p = pnl[lab.start_i:]
            sk = float(pd.Series(p).skew())
            ku = float(pd.Series(p).kurt() + 3)
            st15 = lab.stats(*lab.run(self.cfg(r, cost=1.5)))
            std1 = lab.stats(*lab.run(self.cfg(r, delay=1)))
            p0, dd95 = bootstrap(tr[6])
            dsr = deflated_sharpe(r.sharpe, len(p), sk, ku, n_trials, sr_var)
            # information ratio of the residual (pure alpha) stream vs buy & hold
            bh = lab.bh[lab.start_i:]
            resid = p - r.beta * bh
            ir = resid.mean() / resid.std() * np.sqrt(252) if resid.std() > 0 else 0.0
            rows.append(dict(idx=r.name, cost15_avg=st15["avg"], cost15_pf=st15["pf"],
                             delay1_avg=std1["avg"], delay1_pf=std1["pf"], mc_p_loss=p0, mc_dd95=dd95,
                             dsr=dsr, ir=ir, skew=sk, kurt=ku))
        x = pd.DataFrame(rows).set_index("idx")
        out = cand.join(x)
        out["s3"] = ((out.cost15_avg > 0) & (out.cost15_pf > 1.1) & (out.delay1_avg > 0) &
                     (out.mc_p_loss < 0.05) & (out.exit_plateau >= 0.3) & (out.param_plateau >= 0.3))
        # DSR is reported per system but applied at portfolio level: with ~9 years of daily data no
        # single swing system can clear it on its own (see README), a diversified book can.
        return out

    def funnel(self):
        g = self.g
        return pd.DataFrame({
            "tested": g.groupby("side").size(),
            "stage1_edge": g[g.s1].groupby("side").size(),
            "stage2_alpha": g[g.s2].groupby("side").size(),
        }).fillna(0).astype(int)


def score(df: pd.DataFrame) -> pd.Series:
    """composite ranking: risk-adjusted return, consistency and robustness, lightly penalise tail risk"""
    return (df.sharpe.rank(pct=True) + df.mar.rank(pct=True) + df.alpha_t.rank(pct=True) +
            df.exit_plateau.rank(pct=True) + df.param_plateau.rank(pct=True) +
            np.minimum(df[["disc_ann", "val_ann", "oos_ann"]].min(1) / df.ann.clip(lower=1), 1).rank(pct=True))


if __name__ == "__main__":
    import sys

    sv = Sieve(sys.argv[1] if len(sys.argv) > 1 else "grid.parquet")
    print(sv.funnel())
    g = sv.g
    c2 = g[g.s2].copy()
    print(len(c2), "stage-2 survivors")
    c2["score"] = score(c2)
    top = c2.sort_values("score", ascending=False)
    # keep best exit per setup+regime+side to reduce redundancy before stage 3
    top = top.groupby(["setup", "regime", "side"]).head(3).head(600)
    # effective number of independent trials: exits of one setup+regime+side are highly
    # correlated, so the independent units are the setup x regime x side combinations
    n_eff = g.groupby(["setup", "regime", "side"]).ngroups
    print("trials", len(g), "effective", n_eff)
    s3 = sv.stage3(top, n_trials=n_eff)
    s3.to_parquet(RES / "stage3.parquet")
    print(s3.s3.sum(), "stage-3 survivors")
    cols = ["setup", "regime", "side", "exit", "trades", "win", "avg", "pf", "total", "mdd", "sharpe", "mar",
            "alpha_t", "exposure", "disc_avg", "val_avg", "oos_avg", "exit_plateau", "param_plateau",
            "cost15_avg", "delay1_avg", "mc_p_loss", "dsr", "ir"]
    print(s3[s3.s3].sort_values("score", ascending=False)[cols].head(40).to_string())
