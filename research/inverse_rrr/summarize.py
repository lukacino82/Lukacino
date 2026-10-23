"""Summaries of the inverse-RRR grid: per combo mean/t per period, edge over BASE, robust selection."""
from __future__ import annotations
import os, numpy as np, pandas as pd
DATA = "/tmp/claude-0/data"; OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

def label(m):
    t = 18 * 60 + int(m); return f"{t // 60 % 24:02d}:{t % 60:02d}"

def main():
    G = pd.read_parquet(os.path.join(DATA, "irr_grid.parquet"))
    keys = ["scale", "side", "hz", "rule", "slot", "tp", "sl"]
    W = G.pivot_table(index=keys, columns="p", values=["n", "s", "s2", "w", "tp", "sl"] if False else ["n", "s", "s2", "w"], aggfunc="sum")
    W.columns = [f"{a}_{b}" for a, b in W.columns]
    W = W.fillna(0)
    out = pd.DataFrame(index=W.index)
    infl = np.where(W.index.get_level_values("hz") == "end5", np.sqrt(5), 1.0)
    for p in ("DISC", "VAL", "OOS"):
        n = W[f"n_{p}"]; m = W[f"s_{p}"] / n.replace(0, np.nan)
        v = (W[f"s2_{p}"] / n.replace(0, np.nan) - m ** 2) * n / (n - 1).replace(0, np.nan)
        out[f"n_{p}"] = n; out[f"exp_{p}"] = m; out[f"t_{p}"] = m / np.sqrt(v / n) / infl; out[f"win_{p}"] = W[f"w_{p}"] / n.replace(0, np.nan)
    n = W[[f"n_{p}" for p in ("DISC", "VAL", "OOS")]].sum(axis=1); s = W[[f"s_{p}" for p in ("DISC", "VAL", "OOS")]].sum(axis=1)
    s2 = W[[f"s2_{p}" for p in ("DISC", "VAL", "OOS")]].sum(axis=1); w = W[[f"w_{p}" for p in ("DISC", "VAL", "OOS")]].sum(axis=1)
    m = s / n; v = (s2 / n - m ** 2) * n / (n - 1)
    out["n"] = n; out["exp"] = m; out["t"] = m / np.sqrt(v / n) / infl; out["win"] = w / n
    out = out.reset_index()
    base = out[out.rule == "BASE"].set_index(["scale", "side", "hz", "slot", "tp", "sl"])
    k = ["scale", "side", "hz", "slot", "tp", "sl"]
    for c in ("exp", "exp_DISC", "exp_VAL", "exp_OOS", "win"):
        out["base_" + c] = base[c].reindex(pd.MultiIndex.from_frame(out[k])).to_numpy()
    out["edge"] = out.exp - out.base_exp
    for p in ("DISC", "VAL", "OOS"):
        out[f"edge_{p}"] = out[f"exp_{p}"] - out[f"base_exp_{p}"]
    out["time"] = out.slot.map(label)
    out["rw_win"] = out.sl / (out.tp + out.sl)            # random-walk probability that TP comes first
    out.to_parquet(os.path.join(DATA, "irr_summary.parquet"))
    rob = out[(out.rule != "BASE") & (out.n_VAL >= 30) & (out.n_OOS >= 30) & (out.t_DISC >= 3) &
              (out.exp_DISC > 0) & (out.exp_VAL > 0) & (out.exp_OOS > 0) & (out.edge_DISC > 0) & (out.edge_VAL > 0) & (out.edge_OOS > 0)]
    rob.to_csv(os.path.join(OUT, "robust.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print("combos", len(out), "non-base", (out.rule != "BASE").sum(), "robust", len(rob))
    c = ["scale", "side", "hz", "rule", "time", "tp", "sl", "n", "win", "rw_win", "exp", "edge", "t_DISC", "exp_DISC", "exp_VAL", "exp_OOS", "edge_OOS"]
    print(rob.sort_values("t", ascending=False)[c].head(60).round(3).to_string())
    print(rob.groupby(["scale", "side", "hz"]).size())
    print(rob.groupby("rule").size().sort_values(ascending=False).head(20))
    print(rob.groupby("time").size().sort_values(ascending=False).head(20))
    print((rob.tp / rob.sl).describe())

if __name__ == "__main__":
    main()
