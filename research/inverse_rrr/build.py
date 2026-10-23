"""Build entries (every 30 minutes of the globex day up to 15:30 ET, long and short) and run the inverse-RRR
engine for two horizons (RTH close of the same session, 5 sessions) and two scalings (points, points at ATR 50).
Saves /tmp/claude-0/data/irr_<scale>.npz with first-hit times plus a parquet with the entry table.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
from irr_engine import load_1m, run, TPS, SLS  # noqa: E402

DATA = "/tmp/claude-0/data"
SLOTS = np.arange(0, 1320, 30)            # minutes since 18:00 of previous day: 18:00 ... 15:30 ET


def slot_label(m):
    hh = (18 * 60 + m) // 60 % 24; mm = (18 * 60 + m) % 60
    return f"{hh:02d}:{mm:02d}"


def entries_table(X):
    import features as F
    T = F.load()["T"]
    gday = X.gday.astype("datetime64[D]")
    days, first = np.unique(gday, return_index=True)
    absmin = (gday.astype(np.int64) * 1440 - 360 + X.gmin).astype(np.int64)
    rth = (X.gmin >= 930) & (X.gmin < 1320)
    idx = np.flatnonzero(rth)
    dpos = np.searchsorted(days, gday[idx])
    last = np.full(len(days), -1); np.maximum.at(last, dpos, idx)
    last = np.maximum.accumulate(last)
    # entries: first bar of each slot
    key = np.isin(X.gmin, SLOTS)
    ei = np.flatnonzero(key)
    ed = np.searchsorted(days, gday[ei])
    eod = last[ed] + 1
    d5 = np.minimum(ed + 4, len(days) - 1)
    end5 = last[d5] + 1
    ok = (eod > ei) & (last[ed] >= 0)
    ei, ed, eod, end5 = ei[ok], ed[ok], eod[ok], end5[ok]
    # previous 60 / 30 minute move (open of entry bar vs open of the bar 60 / 30 minutes earlier)
    def prev_move(mins):
        j = np.searchsorted(absmin, absmin[ei] - mins)
        good = (j < len(absmin)) & (absmin[np.minimum(j, len(absmin) - 1)] == absmin[ei] - mins)
        return np.where(good, X.o[ei] - X.o[np.minimum(j, len(absmin) - 1)], np.nan)
    E = pd.DataFrame({"i": ei, "eod": eod, "end5": end5, "gday": days[ed], "slot": X.gmin[ei]})
    E["m60"] = prev_move(60); E["m30"] = prev_move(30)
    # session-to-date move: entry open vs previous RTH close
    Td = T.reindex(pd.to_datetime(E.gday))
    E["gap_prev_close"] = X.o[ei] - T.C.shift().reindex(pd.to_datetime(E.gday)).to_numpy()
    E["atr"] = T.ATR.shift().reindex(pd.to_datetime(E.gday)).to_numpy()          # previous day's ATR
    E["bull"] = (T.C > T.ma200).shift().reindex(pd.to_datetime(E.gday)).to_numpy()
    E["dow"] = pd.to_datetime(E.gday).dt.dayofweek.to_numpy()
    E["year"] = pd.to_datetime(E.gday).dt.year.to_numpy()
    E = E[np.isfinite(E.atr)].reset_index(drop=True)
    return E


def main():
    t0 = time.time()
    X = load_1m()
    E = entries_table(X)
    E.to_parquet(os.path.join(DATA, "irr_entries.parquet"))
    print("entries", len(E), round(time.time() - t0), "s")
    for scale_name in ("pts", "atr50"):
        sc = np.ones(len(E)) if scale_name == "pts" else (E.atr.to_numpy() / 50.0)
        out = {}
        for side in (1, -1):
            for hz in ("eod", "end5"):
                t1 = time.time()
                t_tp, t_sl, cp = run(X, E.i.to_numpy(), E[hz].to_numpy(), np.full(len(E), side), sc)
                tag = f"{'L' if side > 0 else 'S'}_{hz}"
                out[f"tp_{tag}"] = t_tp; out[f"sl_{tag}"] = t_sl; out[f"cp_{tag}"] = cp
                print(scale_name, tag, round(time.time() - t1), "s")
        np.savez(os.path.join(DATA, f"irr_{scale_name}.npz"), **out)
    print("done", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
