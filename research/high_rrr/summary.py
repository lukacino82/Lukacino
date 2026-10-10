"""Summaries of the filter search (real vs shuffled-context null)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from search import robust  # noqa: E402
from engine import expected_longest  # noqa: E402

OUT = os.path.join(HERE, "out")


def load(name):
    return pd.read_parquet(os.path.join(OUT, f"search_{name}.parquet"))


def var_effects(R):
    """single filters: mean change of win rate (P&L > 0) and expectancy vs baseline, per period."""
    S = R[~R.filt.str.contains("&") & (R.filt != "(bez filtru)")].copy()
    for p in ("DISC", "VAL", "TEST"):
        S[f"dwin_{p}"] = S[f"win_{p}"] - S[f"base_win_{p}"]
        S[f"dexp_{p}"] = S[f"exp_{p}"] - S[f"base_exp_{p}"]
    g = S.groupby("filt")
    out = g[[f"dwin_{p}" for p in ("DISC", "VAL", "TEST")] + [f"dexp_{p}" for p in ("DISC", "VAL", "TEST")]].mean()
    out["configs"] = g.size()
    out["consistent"] = (np.sign(out.dwin_DISC) == np.sign(out.dwin_VAL)) & (np.sign(out.dwin_DISC) == np.sign(out.dwin_TEST))
    out["min_dwin"] = out[["dwin_DISC", "dwin_VAL", "dwin_TEST"]].min(axis=1)
    out["max_dwin"] = out[["dwin_DISC", "dwin_VAL", "dwin_TEST"]].max(axis=1)
    return out.sort_values("min_dwin", ascending=False)


def tests_table(R):
    S = R[R.entry.str.startswith(("TEST", "SWEEP")) & R.filt.str.fullmatch(r"tests=\d")].copy()
    S["n_tests"] = S.filt.str[-1].astype(int)
    S["fam"] = S.entry.str.split(" · ").str[0]
    S["side"] = S.entry.str.split(" · ").str[2]
    g = S.groupby(["fam", "side", "n_tests"])
    return g.agg(configs=("exp_ALL", "size"), win=("win_ALL", "mean"), base_win=("base_win_ALL", "mean"),
                 exp=("exp_ALL", "mean"), base_exp=("base_exp_ALL", "mean"),
                 exp_DISC=("exp_DISC", "mean"), exp_VAL=("exp_VAL", "mean"), exp_TEST=("exp_TEST", "mean")).reset_index()


if __name__ == "__main__":
    R = load("real")
    N = load("null1")
    rb, nb = robust(R), robust(N)
    print("evaluated real", len(R), "null", len(N))
    print("robust real", len(rb), "unique (entry,filt)", rb.groupby(["entry", "filt"]).ngroups,
          "| null", len(nb), nb.groupby(["entry", "filt"]).ngroups)
    pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 70); pd.set_option("display.max_rows", 200)
    ve = var_effects(R)
    print(ve.round(4).head(25)); print(ve.round(4).tail(15))
    tt = tests_table(R)
    print(tt.round(3).to_string())
    c = ["entry", "hz", "sl", "rr", "filt", "n_DISC", "n_VAL", "n_TEST", "exp_DISC", "exp_VAL", "exp_TEST", "t_DISC", "t_VAL", "t_TEST",
         "win_ALL", "base_win_ALL", "tp_ALL", "longest_ALL", "base_longest_ALL"]
    top = rb.sort_values("t_TEST", ascending=False).drop_duplicates(["entry", "filt"]).head(40)
    print(top[c].round(3).to_string())
    ve.to_csv(os.path.join(OUT, "var_effects.csv"))
    tt.to_csv(os.path.join(OUT, "tests_table.csv"), index=False)
    rb.to_csv(os.path.join(OUT, "robust_real.csv"), index=False)
    nb.to_csv(os.path.join(OUT, "robust_null.csv"), index=False)
