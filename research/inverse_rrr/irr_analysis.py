"""Evaluate pre-defined entry rules over the full TP x SL grid (including TP < SL).

Rules (decided before looking at results):
  BASE        every 30-minute slot, no condition (= random entry benchmark for that slot)
  UP_x        previous 60 minutes rose >= x points          (momentum)
  DN_x        previous 60 minutes fell >= x points          (dip)
  DN_x_BULL   DN_x and ES above its 200-day MA (dip in an uptrend)
  UP_x_BULL   UP_x and above the 200-day MA
  GAPDN_x_BULL entry price >= x points below the previous RTH close, above the 200-day MA
x in {5, 10, 15, 20} points (in the atr50 scaling x is multiplied by ATR/50 like the TP and SL).

Periods: DISC 2008-2017, VAL 2018-2021, OOS 2022-2026. Every rule is compared with BASE of the same slot,
side, TP, SL and horizon (edge = rule minus random entry).
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from irr_engine import TPS, SLS, COST  # noqa: E402

DATA = "/tmp/claude-0/data"
OUT = os.path.join(HERE, "out")
XS = (5, 10, 15, 20)


def period(y):
    return np.where(y <= 2017, "DISC", np.where(y <= 2021, "VAL", "OOS"))


def rule_masks(E, scale):
    m60 = E.m60.to_numpy() / scale; gap = E.gap_prev_close.to_numpy() / scale
    bull = E.bull.fillna(False).to_numpy().astype(bool)
    R = {"BASE": np.ones(len(E), bool)}
    for x in XS:
        R[f"UP_{x}"] = m60 >= x
        R[f"DN_{x}"] = m60 <= -x
        R[f"UP_{x}_BULL"] = (m60 >= x) & bull
        R[f"DN_{x}_BULL"] = (m60 <= -x) & bull
        R[f"GAPDN_{x}_BULL"] = (gap <= -x) & bull
    return R


def stats_block(pnl, code, key, per):
    """group by key (rule-slot id) and period -> n, sum, sumsq, wins"""
    df = pd.DataFrame({"k": key, "p": per, "x": pnl, "x2": pnl * pnl, "w": (pnl > 0).astype(np.int32),
                       "tp": (code == 1).astype(np.int32), "sl": (code == -1).astype(np.int32)})
    g = df.groupby(["k", "p"], sort=False).agg(n=("x", "size"), s=("x", "sum"), s2=("x2", "sum"), w=("w", "sum"),
                                                tp=("tp", "sum"), sl=("sl", "sum"))
    return g


def main():
    t0 = time.time()
    E = pd.read_parquet(os.path.join(DATA, "irr_entries.parquet"))
    per = period(E.year.to_numpy())
    slots = E.slot.to_numpy()
    rows = []
    for scale_name in ("pts", "atr50"):
        Z = np.load(os.path.join(DATA, f"irr_{scale_name}.npz"))
        scale = np.ones(len(E)) if scale_name == "pts" else E.atr.to_numpy() / 50.0
        R = rule_masks(E, scale)
        rnames = list(R)
        # one long key array: rule id * 100 + slot index, over the stacked rows of all rules
        sel_idx = np.concatenate([np.flatnonzero(R[r]) for r in rnames])
        sel_rule = np.concatenate([np.full(R[r].sum(), j) for j, r in enumerate(rnames)])
        slot_ix = np.searchsorted(np.unique(slots), slots)
        key = sel_rule * 100 + slot_ix[sel_idx]
        pr = per[sel_idx]
        for side in ("L", "S"):
            for hz in ("eod", "end5"):
                ttp = Z[f"tp_{side}_{hz}"][sel_idx]; tsl = Z[f"sl_{side}_{hz}"][sel_idx]; cp = Z[f"cp_{side}_{hz}"][sel_idx]
                sc = scale[sel_idx]
                for it, tp in enumerate(TPS):
                    a = ttp[:, it]
                    for js, sl in enumerate(SLS):
                        b = tsl[:, js]
                        win = a < b; loss = (b <= a) & (b < 2**31 - 1)
                        pnl = np.where(win, tp * sc, np.where(loss, -sl * sc, cp)) - COST
                        code = np.where(win, 1, np.where(loss, -1, 0))
                        g = stats_block(pnl, code, key, pr).reset_index()
                        g["scale"] = scale_name; g["side"] = side; g["hz"] = hz; g["tp"] = tp; g["sl"] = sl
                        rows.append(g)
                print(scale_name, side, hz, round(time.time() - t0), "s", flush=True)
    G = pd.concat(rows, ignore_index=True)
    G["rule"] = np.array(rnames)[G.k // 100]
    G["slot"] = np.unique(slots)[G.k % 100]
    G = G.drop(columns="k")
    G.to_parquet(os.path.join(DATA, "irr_grid.parquet"))
    print("rows", len(G), round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
