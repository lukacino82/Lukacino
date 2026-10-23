"""DISC-only selection on the ATR grid, family / plateau check, and an automated portfolio of the selected
inverse-RRR signals compared with buy & hold ES.

Units: ATR (previous day's ATR14) per trade, after 0.5 point cost. t-stats get one extra full SL loss
("black swan" penalty) and are deflated by sqrt(5) on the 5-day horizon (overlapping trades).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
from irr_engine import TPS, SLS, COST, load_1m  # noqa: E402
from atr_signals import rules, label, PER, INT  # noqa: E402

DATA = "/tmp/claude-0/data"
OUT = os.path.join(HERE, "out")


def stats(G):
    infl = np.where(G.hz == "end5", np.sqrt(5), 1.0)
    for p in PER:
        n, s, s2 = G[f"n_{p}"], G[f"s_{p}"], G[f"s2_{p}"]
        G[f"exp_{p}"] = s / n.replace(0, np.nan)
        L = G.sl + 0.01
        n1, s_1, s2_1 = n + 1, s - L, s2 + L * L
        m = s_1 / n1; v = (s2_1 / n1 - m * m) * n1 / np.maximum(n1 - 1, 1)
        G[f"t_{p}"] = m / np.sqrt(np.maximum(v, 1e-12) / n1) / infl
        G[f"win_{p}"] = G[f"w_{p}"] / n.replace(0, np.nan)
    n = G.n_DISC + G.n_VAL + G.n_OOS
    G["n"] = n; G["exp"] = (G.s_DISC + G.s_VAL + G.s_OOS) / n
    base = G[G.rule == "BASE"].set_index(["slot", "side", "hz", "tp", "sl"])
    k = pd.MultiIndex.from_frame(G[["slot", "side", "hz", "tp", "sl"]])
    for p in PER:
        G[f"edge_{p}"] = G[f"exp_{p}"] - base[f"exp_{p}"].reindex(k).to_numpy()
    G["time"] = G.slot.map(label)
    G["rw_win"] = G.sl / (G.tp + G.sl)
    G["inv"] = G.sl >= 2 * G.tp
    return G


def selection(G):
    C = G[(G.rule != "BASE") & (G.n_DISC >= 60) & (G.n_VAL >= 20) & (G.n_OOS >= 20)]
    groups = {
        "vše": C,
        "long, obrácené RRR (SL ≥ 2×TP)": C[(C.side == "L") & C.inv],
        "long, obrácené RRR, do close": C[(C.side == "L") & C.inv & (C.hz == "eod")],
        "long, obrácené RRR, 5 dní": C[(C.side == "L") & C.inv & (C.hz == "end5")],
        "long, RRR ≤ 1:1 (TP ≥ SL)": C[(C.side == "L") & (C.tp >= C.sl)],
        "short, obrácené RRR": C[(C.side == "S") & C.inv],
        "short, vše": C[C.side == "S"],
    }
    rows = []
    for name, D in groups.items():
        ref = (D.edge_OOS > 0).mean()
        for top in (20, 100, 500):
            T = D.sort_values("t_DISC", ascending=False).head(top)
            rows.append(dict(skupina=name, top=top, kombinaci=len(D), t_DISC=T.t_DISC.median(),
                             exp_DISC=T.exp_DISC.mean(), exp_VAL=T.exp_VAL.mean(), exp_OOS=T.exp_OOS.mean(),
                             edge_DISC=T.edge_DISC.mean(), edge_VAL=T.edge_VAL.mean(), edge_OOS=T.edge_OOS.mean(),
                             OOS_exp_kladne=(T.exp_OOS > 0).mean(), OOS_edge_kladne=(T.edge_OOS > 0).mean(),
                             VAL_a_OOS_edge_kladne=((T.edge_VAL > 0) & (T.edge_OOS > 0)).mean(),
                             nahodny_vyber_OOS_edge_kladne=ref))
    S = pd.DataFrame(rows)
    S.round(3).to_csv(os.path.join(OUT, "atr_selection.csv"), index=False)
    return S, C


def families(C):
    """rule-level: aggregate all slots x TP x SL of a rule (long, inverse) -> does the rule carry information?"""
    D = C[(C.side == "L") & C.inv].copy()
    agg = D.groupby(["rule", "hz"]).agg(kombinaci=("edge_DISC", "size"), edge_DISC=("edge_DISC", "mean"),
                                        edge_VAL=("edge_VAL", "mean"), edge_OOS=("edge_OOS", "mean"),
                                        kladne_DISC=("edge_DISC", lambda v: (v > 0).mean()),
                                        kladne_VAL=("edge_VAL", lambda v: (v > 0).mean()),
                                        kladne_OOS=("edge_OOS", lambda v: (v > 0).mean())).reset_index()
    agg["vsude"] = (agg.edge_DISC > 0) & (agg.edge_VAL > 0) & (agg.edge_OOS > 0)
    agg = agg.sort_values("edge_DISC", ascending=False)
    agg.round(4).to_csv(os.path.join(OUT, "atr_families.csv"), index=False)
    # family x time: which hours carry the edge (DISC-chosen families)
    return agg


def pick_signals(C, k=25):
    """portfolio candidates chosen on DISC only: long inverse RRR, best TP/SL per (rule, slot, hz), distinct
    rule families, t_DISC >= 2.5 and edge_DISC > 0"""
    D = C[(C.side == "L") & C.inv & (C.edge_DISC > 0) & (C.t_DISC >= 2.5) & (C.rule != "BASE")].copy()
    D = D.sort_values("t_DISC", ascending=False).drop_duplicates(["rule", "slot", "hz"])
    D["fam"] = D.rule.str.replace(r"_[BR]$", "", regex=True).str.replace(r"_[0-9.]+$", "", regex=True)
    D = D.drop_duplicates(["fam", "slot"]).head(k)
    return D


def trades_for(E, Z, X_gday, R, sig):
    """per-trade table for one signal (rule, slot, side=L, hz, tp, sl in ATR)"""
    m = R[sig.rule] & (E.slot.to_numpy() == sig.slot)
    it = int(np.flatnonzero(np.isclose(TPS / 50, sig.tp))[0]); js = int(np.flatnonzero(np.isclose(SLS / 50, sig.sl))[0])
    hz = sig.hz
    a = Z[f"tp_L_{hz}"][m, it]; b = Z[f"sl_L_{hz}"][m, js]; cp = Z[f"cp_L_{hz}"][m]
    atr = E.atr.to_numpy()[m]; sc = atr / 50
    win = a < b; loss = (b <= a) & (b < INT)
    pts = np.where(win, TPS[it] * sc, np.where(loss, -SLS[js] * sc, cp)) - COST
    end = E[hz].to_numpy()[m] - 1
    ex = np.minimum(np.minimum(a, b), end)
    t = pd.DataFrame({"entry": pd.to_datetime(E.gday.to_numpy()[m]), "exit": pd.to_datetime(X_gday[ex]),
                      "pts": pts, "atr": atr, "risk_pts": SLS[js] * sc + COST, "code": np.where(win, 1, np.where(loss, -1, 0))})
    # one open trade per signal
    keep, busy = [], pd.Timestamp("1900-01-01")
    for i, r in enumerate(t.itertuples()):
        if r.entry > busy or (hz == "eod"):
            keep.append(i); busy = r.exit
    return t.iloc[keep].reset_index(drop=True)


def portfolio(tr, close, risk=0.005, start="2018-01-01", cap=1.0):
    """equity in % with risk-based sizing: contracts = risk*equity / (risk_pts*$50); P&L booked on exit day.
    cap = max total risk open per day as share of equity (simple guard: scale down if exceeded)"""
    tr = tr[tr.entry >= start].sort_values("entry")
    days = close.loc[start:].index
    eq = 1.0; curve = []
    by_exit = {d: g for d, g in tr.groupby("exit")}
    by_entry = {d: g for d, g in tr.groupby("entry")}
    open_r = {}
    for d in days:
        if d in by_entry:
            g = by_entry[d]
            for i, r in g.iterrows():
                open_r[i] = risk * eq / r.risk_pts            # $ per point / 50 -> units of equity per point
        if d in by_exit:
            for i, r in by_exit[d].iterrows():
                u = open_r.pop(i, risk * eq / r.risk_pts)
                eq += u * r.pts
        curve.append(eq)
    return pd.Series(curve, index=days)


def perf(s):
    r = s.pct_change().dropna()
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    dd = (s / s.cummax() - 1).min()
    return dict(CAGR=cagr, vol=r.std() * np.sqrt(252), sharpe=r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan,
                maxDD=dd)


def main():
    G = stats(pd.read_parquet(os.path.join(DATA, "atr_grid.parquet")))
    S, C = selection(G)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(S.round(3).to_string())
    F = families(C)
    print(F.head(30).round(3).to_string())
    print("families with edge>0 in all periods:", F.vsude.sum(), "of", len(F))
    P = pick_signals(C)
    cols = ["rule", "time", "hz", "tp", "sl", "n_DISC", "n_VAL", "n_OOS", "t_DISC", "exp_DISC", "exp_VAL", "exp_OOS",
            "edge_DISC", "edge_VAL", "edge_OOS", "win_DISC", "win_OOS", "rw_win"]
    print(P[cols].round(3).to_string())
    P[cols].round(4).to_csv(os.path.join(OUT, "atr_portfolio_signals.csv"), index=False)
    # --- automated portfolio
    E = pd.read_parquet(os.path.join(DATA, "atr_entries.parquet"))
    R = rules(E)
    Z = np.load(os.path.join(DATA, "irr_atr50.npz"))
    X = load_1m()
    Xg = X.gday.astype("datetime64[D]")
    trs = []
    for sig in P.itertuples():
        t = trades_for(E, Z, Xg, R, sig); t["sig"] = f"{sig.rule} {sig.time} {sig.hz} {sig.tp:.2f}/{sig.sl:.2f}"
        trs.append(t)
    TR = pd.concat(trs, ignore_index=True)
    TR.to_parquet(os.path.join(DATA, "atr_trades.parquet"))
    import features as Fe
    T = Fe.load()["T"]
    close = T.C
    res = {}
    for start, name in (("2009-01-01", "2009–2026 (výběr v DISC)"), ("2018-01-01", "2018–2026 (mimo výběr)"),
                        ("2022-01-01", "2022–2026 (OOS)")):
        bh = close.loc[start:] / close.loc[start:].iloc[0]
        row = {"B&H ES": perf(bh)}
        for rk in (0.0025, 0.005, 0.01):
            eqs = portfolio(TR, close, risk=rk, start=start)
            row[f"systém riziko {rk*100:.2f} %"] = perf(eqs)
            if rk == 0.005:
                comb = (bh.pct_change().fillna(0) + eqs.pct_change().fillna(0) + 1).cumprod()
                row["B&H + systém 0,5 %"] = perf(comb)
        res[name] = row
        print(name); print(pd.DataFrame(row).T.round(3).to_string())
    # yearly table at 0.5 % risk vs B&H
    eq = portfolio(TR, close, risk=0.005, start="2009-01-01")
    yr = pd.DataFrame({"systém %": eq.groupby(eq.index.year).last().pct_change() * 100,
                       "B&H %": close.groupby(close.index.year).last().pct_change() * 100})
    yr.loc[2009, "systém %"] = (eq.groupby(eq.index.year).last().iloc[0] - 1) * 100
    yr["obchodů"] = TR[TR.entry >= "2009-01-01"].groupby(TR.entry.dt.year).size()
    yr["win %"] = TR.groupby(TR.entry.dt.year).code.apply(lambda c: (c == 1).mean() * 100)
    yr["SL zásahů"] = TR.groupby(TR.entry.dt.year).code.apply(lambda c: (c == -1).sum())
    yr = yr.loc[2009:]
    print(yr.round(1).to_string())
    yr.round(2).to_csv(os.path.join(OUT, "atr_portfolio_years.csv"))
    corr = pd.concat([eq.pct_change(), close.loc["2009":].pct_change()], axis=1).corr().iloc[0, 1]
    print("korelace denních výnosů se ES", round(corr, 3))
    json.dump(dict(perf={k: {kk: {a: float(b) for a, b in vv.items()} for kk, vv in v.items()} for k, v in res.items()},
                   corr=float(corr), n_trades=int(len(TR)),
                   eq=dict(d=[str(x)[:10] for x in eq.index[::5]], e=np.round(eq.to_numpy()[::5], 4).tolist()),
                   bh=dict(d=[str(x)[:10] for x in close.loc["2009":].index[::5]],
                           e=np.round((close.loc["2009":] / close.loc["2009":].iloc[0]).to_numpy()[::5], 4).tolist())),
              open(os.path.join(OUT, "atr_portfolio.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
