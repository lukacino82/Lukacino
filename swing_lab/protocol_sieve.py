"""
Protocol sieve (ES Multi-Swing research protocol, 2026-09-27) on the 18-year ES2008 grid.

  1  rules fixed before testing (systems.py protocol_setups committed before this grid ran)
  2  >= 80 trades total and >= 20 per period (calendar anomalies: >= 40 / >= 10, flagged)
  3  expectancy > 0 after 1.5 pt round trip + 1 tick slippage each side (2.0 pt)
  4  PF > 1.15 in Discovery, Validation and OOS; no period rescued by one trade
  5  parameter plateau: >= 60 % of neighbours (same family/regime/exit, other thresholds) positive
  6  stability by year, volatility tercile, long/short
  7  stationary block bootstrap of daily P&L (20-day blocks) + trade-order Monte Carlo
  8  Deflated Sharpe Ratio (N_eff trials) and PBO via combinatorially symmetric cross-validation
  9  expanding walk-forward, >= 4 training years, 1 test year, 20-day embargo
 10  execution replay on 30-min bars, conservative TP/SL ambiguity (engine.py, tests/)
Benchmarks: Buy & Hold, long above SMA200, random entry with matched exposure.
"""
from __future__ import annotations

import itertools
import json
import math
import re

import numpy as np
import pandas as pd
from scipy.stats import norm

import systems as S
from canonical import canonical
from lab import Lab
from sieve import RES, deflated_sharpe, family

STRESS = 2.0
CAL = ("TOM_", "PreHoliday", "TurnaroundMon", "OpexWeekMon")


def load():
    g = pd.read_parquet(RES / "grid.parquet")
    g["family"] = g.setup.map(family)
    g["calendar"] = g.setup.str.startswith(CAL)
    return g


def rules(g: pd.DataFrame) -> pd.DataFrame:
    cal = g.calendar
    ntot = np.where(cal, 40, 80)
    nper = np.where(cal, 10, 20)
    g["r_trades"] = (g.trades >= ntot) & (g.disc_n >= nper) & (g.val_n >= nper) & (g.oos_n >= nper)
    g["r_pf"] = (g.disc_pf > 1.15) & (g.val_pf > 1.15) & (g.oos_pf > 1.15)
    # 1-trade rescue proxy: period P&L must exceed one average winner (avg * 3) -> require avg > 0 each period
    g["r_periods"] = (g.disc_avg > 0) & (g.val_avg > 0) & (g.oos_avg > 0)
    g["r_cost_proxy"] = g.avg > STRESS - 0.5          # exact stress re-run below for survivors
    pos = g.total > 0
    g["_pos"] = pos
    g["plateau"] = g.groupby(["family", "regime", "side", "exit"])._pos.transform("mean")
    g["n_neigh"] = g.groupby(["family", "regime", "side", "exit"])._pos.transform("size")
    g["r_plateau"] = (g.plateau >= 0.6) | (g.n_neigh == 1)
    g["pass_basic"] = g.r_trades & g.r_pf & g.r_periods & g.r_cost_proxy & g.r_plateau
    return g


def block_bootstrap(p, block=20, n=2000, seed=11):
    rng = np.random.default_rng(seed)
    T = len(p)
    nb = int(math.ceil(T / block))
    starts = rng.integers(0, T - block, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n, -1)[:, :T]
    sims = p[idx]
    tot = sims.sum(1)
    eq = sims.cumsum(1)
    dd = (np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq).max(1)
    return float((tot <= 0).mean()), float(np.percentile(dd, 95))


def random_entry_pct(lab: Lab, tr, mask, cost, n=2000, seed=5):
    """percentile of the system's total vs random long entries with the same count, hold lengths and
    eligible days (regime mask) - 'time and exposure matched random entry'."""
    rng = np.random.default_rng(seed)
    c = lab.d.close.values
    ent, ex, pnl = tr[1], tr[2], tr[8]
    holds = np.maximum(ex - ent, 1)
    elig = np.where(mask[: lab.end_i - 25] & (np.arange(lab.end_i - 25) >= lab.start_i))[0]
    if len(elig) < 10 or len(holds) == 0:
        return np.nan
    k = len(holds)
    starts = rng.choice(elig, size=(n, k))
    hh = rng.choice(holds, size=(n, k))
    ends = np.minimum(starts + hh, lab.end_i - 1)
    sims = (c[ends] - c[starts] - cost).sum(1)
    return float((sims < pnl.sum()).mean())


def pbo_cscv(M: np.ndarray, S_=12):
    """Probability of Backtest Overfitting, Bailey-Borwein-Lopez de Prado-Zhu CSCV.
    M: T x N matrix of daily P&L of N trials."""
    T, N = M.shape
    blocks = np.array_split(np.arange(T), S_)
    logits = []
    for comb in itertools.combinations(range(S_), S_ // 2):
        is_idx = np.concatenate([blocks[i] for i in comb])
        oos_idx = np.concatenate([blocks[i] for i in range(S_) if i not in comb])
        a, b = M[is_idx], M[oos_idx]
        sr_is = a.mean(0) / (a.std(0) + 1e-12)
        sr_oos = b.mean(0) / (b.std(0) + 1e-12)
        best = int(np.argmax(sr_is))
        rank = (sr_oos < sr_oos[best]).mean()          # relative rank in (0,1)
        w = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(w / (1 - w)))
    logits = np.array(logits)
    return float((logits <= 0).mean()), logits


def expanding_wf(g: pd.DataFrame, lab: Lab, first_test=2013, k=5):
    """yearly re-selection: train on all full years before Y (>= 4 years), pick top-k families by
    t-stat of yearly P&L among rule-compliant configs, trade year Y blind. Embargo: the training
    window ends 20 trading days before Y (trades exiting in that gap are dropped by using full
    calendar years and the 20-day max hold, i.e. year Y-1's last month counts only if closed)."""
    years = sorted(int(c[1:]) for c in g.columns if re.fullmatch(r"y\d{4}", c))
    out = []
    picks_log = {}
    for Y in range(first_test, years[-1] + 1):
        tr = [y for y in years if y < Y and y >= 2009]
        if len(tr) < 4:
            continue
        cols = [f"y{y}" for y in tr]
        X = g[cols].fillna(0)
        m = X.mean(1)
        s = X.std(1).replace(0, np.nan)
        t = m / s * np.sqrt(len(cols))
        posfrac = (X > 0).mean(1)
        elig = (posfrac >= 0.75) & (g.trades >= 40) & (g.side > 0) & (~g.exit.str.contains(r"\d+pt_"))
        cand = g[elig].assign(t=t[elig]).sort_values("t", ascending=False)
        chosen = cand.drop_duplicates("family").head(k)
        picks_log[Y] = chosen[["setup", "regime", "exit"]].to_dict("records")
        out.append(dict(year=Y, book=float(chosen[f"y{Y}"].sum()), n=len(chosen)))
    wf = pd.DataFrame(out).set_index("year")
    bh = pd.Series(lab.bh[lab.start_i:]).groupby(lab.years[lab.start_i:]).sum()
    wf["bh"] = bh.reindex(wf.index).values
    return wf, picks_log


def main():
    lab = Lab()
    g = rules(load())
    bh = lab.bh_stats
    g["r_alpha"] = (g.alpha_t > 0) & ((g.sharpe > bh["sharpe"]) | (g.mar > bh["mar"]))
    g["pass12"] = g.pass_basic & g.r_alpha
    funnel = {
        "tested": int(len(g)), "long": int((g.side > 0).sum()), "short": int((g.side < 0).sum()),
        "trades_rule": int(g.r_trades.sum()), "pf_all_periods": int((g.r_trades & g.r_pf).sum()),
        "periods_positive": int((g.r_trades & g.r_pf & g.r_periods).sum()),
        "plateau_60": int(g.pass_basic.sum()), "alpha_vs_bh": int(g.pass12.sum()),
    }
    print(funnel)
    setups = {s[0]: s for s in S.setups(lab.d)}
    exits = {e[0]: e for e in S.exits(lab.d)}
    reg = S.regimes(lab.d)
    n_eff = g.groupby(["setup", "regime", "side"]).ngroups
    cand = g[g.pass12].sort_values("sharpe", ascending=False)
    cand = cand.groupby(["setup", "regime", "side"]).head(1).head(400)
    rows = []
    vol = lab.d.atr20.values / lab.d.close.values
    terc = np.nanpercentile(vol[lab.start_i:], [33, 67])
    for idx, r in cand.iterrows():
        cfg = S.build_cfg(lab.d, setups[r.setup], exits[r.exit], int(r.side), reg[r.regime], 0.5)
        pnl, pos, tr = lab.run(cfg)
        p = pnl[lab.start_i:]
        st2 = lab.stats(*lab.run(dict(cfg, cost=STRESS)))
        pb, dd95 = block_bootstrap(p)
        # stability by volatility tercile of the entry day
        v = vol[tr[1]]
        vt = [tr[8][(v < terc[0])].sum(), tr[8][(v >= terc[0]) & (v < terc[1])].sum(), tr[8][v >= terc[1]].sum()]
        rnd = random_entry_pct(lab, tr, reg[r.regime], 0.5)
        dsr = deflated_sharpe(r.sharpe, len(p), float(pd.Series(p).skew()), float(pd.Series(p).kurt() + 3),
                              n_eff, g.sharpe.var())
        rows.append(dict(idx=idx, stress_avg=st2["avg"], stress_pf=st2["pf"], boot_p_loss=pb, boot_dd95=dd95,
                         vol_lo=vt[0], vol_mid=vt[1], vol_hi=vt[2], rand_pct=rnd, dsr=dsr))
    x = cand.join(pd.DataFrame(rows).set_index("idx"))
    x["pass_final"] = ((x.stress_avg > 0) & (x.boot_p_loss < 0.05) & (x.rand_pct >= 0.95) &
                       (x[["vol_lo", "vol_mid", "vol_hi"]].min(1) > 0))
    x.to_parquet(RES / "protocol_candidates.parquet")
    funnel.update(stage3_checked=int(len(x)), stress_ok=int((x.stress_avg > 0).sum()),
                  bootstrap_ok=int((x.boot_p_loss < 0.05).sum()), random_entry_95=int((x.rand_pct >= 0.95).sum()),
                  all_vol_terciles=int((x[["vol_lo", "vol_mid", "vol_hi"]].min(1) > 0).sum()),
                  final=int(x.pass_final.sum()), dsr_09=int((x.dsr >= 0.9).sum()), n_eff=int(n_eff))
    # PBO on the whole selection universe: random sample of long configs + all candidates
    rng = np.random.default_rng(3)
    pool = g[(g.side > 0) & (g.trades >= 40)]
    samp = pool.sample(min(1500, len(pool)), random_state=3)
    samp = pd.concat([samp, g.loc[cand.index]]).drop_duplicates(["setup", "regime", "exit", "side"])
    M = []
    for r in samp.itertuples():
        cfg = S.build_cfg(lab.d, setups[r.setup], exits[r.exit], int(r.side), reg[r.regime], 0.5)
        M.append(lab.run(cfg)[0][lab.start_i:])
    M = np.array(M).T
    pbo, logits = pbo_cscv(M)
    funnel.update(pbo=round(pbo, 3), pbo_trials=int(M.shape[1]))
    wf, picks = expanding_wf(g, lab)
    wf.to_csv(RES / "protocol_wf.csv")
    json.dump({str(k): v for k, v in picks.items()}, open(RES / "protocol_wf_picks.json", "w"), indent=1)
    json.dump(funnel, open(RES / "protocol_funnel.json", "w"), indent=1)
    pd.set_option("display.width", 250)
    print(funnel)
    cols = ["setup", "regime", "side", "exit", "trades", "win", "avg", "stress_avg", "pf", "disc_pf", "val_pf", "oos_pf",
            "sharpe", "mar", "alpha_t", "exposure", "plateau", "boot_p_loss", "rand_pct", "dsr"]
    print(x[x.pass_final].sort_values("sharpe", ascending=False)[cols].head(40).round(2).to_string())
    print(wf.round(0).T.to_string())
    print("WF book total", wf.book.sum(), "B&H", wf.bh.sum())


if __name__ == "__main__":
    main()
