"""Family-level selection (less overfit than picking single TP/SL/slot combos).

1. A family = (rule, side, horizon). Its DISC score = mean edge vs random entry over all its slots x TP x SL with
   SL >= 2 x TP (inverse RRR) and the share of those combos with positive edge.
2. Families are chosen on DISC only: share positive >= 0.75 and mean edge >= 0.01 ATR.
3. For each chosen family ONE setting is fixed from DISC at the family level: the TP/SL pair with the best mean
   edge over all slots, and the 3 slots with the best mean edge over all inverse TP/SL pairs.
4. All chosen family signals trade automatically; portfolio with risk-based sizing vs buy & hold, by year.
Reference: the same share statistics for all families (what a random family would give).
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
from irr_engine import load_1m  # noqa: E402
from atr_signals import rules, label  # noqa: E402
from atr_select import stats, trades_for, portfolio, perf  # noqa: E402

DATA = "/tmp/claude-0/data"
OUT = os.path.join(HERE, "out")


def main():
    G = stats(pd.read_parquet(os.path.join(DATA, "atr_grid.parquet")))
    C = G[(G.rule != "BASE") & G.inv & (G.n_DISC >= 30)]
    fam = C.groupby(["rule", "side", "hz"]).agg(
        edge_DISC=("edge_DISC", "mean"), edge_VAL=("edge_VAL", "mean"), edge_OOS=("edge_OOS", "mean"),
        pos_DISC=("edge_DISC", lambda v: (v > 0).mean()), pos_VAL=("edge_VAL", lambda v: (v > 0).mean()),
        pos_OOS=("edge_OOS", lambda v: (v > 0).mean()), combos=("edge_DISC", "size")).reset_index()
    chosen = fam[(fam.pos_DISC >= 0.75) & (fam.edge_DISC >= 0.01)].sort_values("edge_DISC", ascending=False)
    ref = dict(all_fam=len(fam), all_both_pos=float(((fam.edge_VAL > 0) & (fam.edge_OOS > 0)).mean()),
               chosen=len(chosen), chosen_both_pos=float(((chosen.edge_VAL > 0) & (chosen.edge_OOS > 0)).mean()),
               chosen_VAL_pos=float((chosen.edge_VAL > 0).mean()), chosen_OOS_pos=float((chosen.edge_OOS > 0).mean()),
               all_VAL_pos=float((fam.edge_VAL > 0).mean()), all_OOS_pos=float((fam.edge_OOS > 0).mean()))
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(ref)
    print(chosen.round(3).to_string())
    fam.round(4).to_csv(os.path.join(OUT, "atr_family_all.csv"), index=False)
    chosen.round(4).to_csv(os.path.join(OUT, "atr_family_chosen.csv"), index=False)
    # fixed setting per family from DISC
    sigs = []
    for f in chosen.itertuples():
        D = C[(C.rule == f.rule) & (C.side == f.side) & (C.hz == f.hz)]
        pair = D.groupby(["tp", "sl"]).edge_DISC.mean().idxmax()
        slots = D.groupby("slot").edge_DISC.mean().sort_values(ascending=False).head(3).index
        for s in slots:
            r = D[(D.slot == s) & (D.tp == pair[0]) & (D.sl == pair[1])]
            if len(r):
                sigs.append(r.iloc[0])
    P = pd.DataFrame(sigs)
    cols = ["rule", "side", "time", "hz", "tp", "sl", "n_DISC", "n_VAL", "n_OOS", "exp_DISC", "exp_VAL", "exp_OOS",
            "edge_DISC", "edge_VAL", "edge_OOS", "win_OOS", "rw_win"]
    print(P[cols].round(3).to_string())
    P[cols].round(4).to_csv(os.path.join(OUT, "atr_family_signals.csv"), index=False)
    # portfolio (long and short signals; trades_for handles long only -> split)
    E = pd.read_parquet(os.path.join(DATA, "atr_entries.parquet"))
    R = rules(E)
    Z = np.load(os.path.join(DATA, "irr_atr50.npz"))
    X = load_1m(); Xg = X.gday.astype("datetime64[D]")
    trs = []
    for sig in P.itertuples():
        t = trades_side(E, Z, Xg, R, sig)
        t["sig"] = f"{sig.side} {sig.rule} {sig.time} {sig.hz} {sig.tp:.2f}/{sig.sl:.2f}"
        trs.append(t)
    TR = pd.concat(trs, ignore_index=True)
    import features as Fe
    close = Fe.load()["T"].C
    res = {}
    for start, name in (("2009-01-01", "2009–2026"), ("2018-01-01", "2018–2026 (mimo výběr)"),
                        ("2022-01-01", "2022–2026 (OOS)")):
        bh = close.loc[start:] / close.loc[start:].iloc[0]
        row = {"B&H ES": perf(bh)}
        for rk in (0.0025, 0.005):
            eqs = portfolio(TR, close, risk=rk, start=start)
            row[f"systém riziko {rk*100:.2f} %"] = perf(eqs)
        comb = (bh.pct_change().fillna(0) + portfolio(TR, close, risk=0.005, start=start).pct_change().fillna(0) + 1).cumprod()
        row["B&H + systém 0,5 %"] = perf(comb)
        res[name] = row
        print(name); print(pd.DataFrame(row).T.round(3).to_string())
    eq = portfolio(TR, close, risk=0.005, start="2009-01-01")
    yl = eq.groupby(eq.index.year).last()
    yr = pd.DataFrame({"systém %": yl.pct_change() * 100, "B&H %": close.groupby(close.index.year).last().pct_change() * 100})
    yr.loc[2009, "systém %"] = (yl.iloc[0] - 1) * 100
    g = TR.groupby(TR.entry.dt.year)
    yr["obchodů"] = g.size(); yr["win %"] = g.code.apply(lambda c: (c == 1).mean() * 100)
    yr["SL zásahů"] = g.code.apply(lambda c: (c == -1).sum())
    yr = yr.loc[2009:]
    print(yr.round(1).to_string())
    yr.round(2).to_csv(os.path.join(OUT, "atr_family_years.csv"))
    per_sig = TR.assign(r=TR.pts / TR.risk_pts, y=TR.entry.dt.year).groupby("sig").apply(
        lambda d: pd.Series({"obchodů": len(d), "R/obchod": d.r.mean(), "R 18–21": d[(d.y >= 2018) & (d.y <= 2021)].r.mean(),
                             "R 22–26": d[d.y >= 2022].r.mean(), "win": (d.code == 1).mean()}))
    print(per_sig.round(3).to_string())
    per_sig.round(4).to_csv(os.path.join(OUT, "atr_family_per_signal.csv"))
    corr = pd.concat([eq.pct_change(), close.loc["2009":].pct_change()], axis=1).corr().iloc[0, 1]
    print("korelace se ES", round(corr, 3))
    json.dump(dict(ref=ref, perf={k: {kk: {a: float(b) for a, b in vv.items()} for kk, vv in v.items()} for k, v in res.items()},
                   corr=float(corr), eq=dict(d=[str(x)[:10] for x in eq.index[::5]], e=np.round(eq.to_numpy()[::5], 4).tolist())),
              open(os.path.join(OUT, "atr_family.json"), "w"), ensure_ascii=False)


def trades_side(E, Z, Xg, R, sig):
    """like trades_for but for either side"""
    from irr_engine import TPS, SLS, COST
    INT = 2**31 - 1
    s = sig.side
    m = R[sig.rule] & (E.slot.to_numpy() == sig.slot)
    it = int(np.flatnonzero(np.isclose(TPS / 50, sig.tp))[0]); js = int(np.flatnonzero(np.isclose(SLS / 50, sig.sl))[0])
    a = Z[f"tp_{s}_{sig.hz}"][m, it]; b = Z[f"sl_{s}_{sig.hz}"][m, js]; cp = Z[f"cp_{s}_{sig.hz}"][m]
    sc = E.atr.to_numpy()[m] / 50
    win = a < b; loss = (b <= a) & (b < INT)
    pts = np.where(win, TPS[it] * sc, np.where(loss, -SLS[js] * sc, cp)) - COST
    end = E[sig.hz].to_numpy()[m] - 1
    ex = np.minimum(np.minimum(a, b), end)
    t = pd.DataFrame({"entry": pd.to_datetime(E.gday.to_numpy()[m]), "exit": pd.to_datetime(Xg[ex]), "pts": pts,
                      "risk_pts": SLS[js] * sc + COST, "code": np.where(win, 1, np.where(loss, -1, 0))})
    keep, busy = [], pd.Timestamp("1900-01-01")
    for i, r in enumerate(t.itertuples()):
        if sig.hz == "eod" or r.entry > busy:
            keep.append(i); busy = r.exit
    return t.iloc[keep].reset_index(drop=True)


if __name__ == "__main__":
    main()
