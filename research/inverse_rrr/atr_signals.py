"""Inverse RRR with ATR-scaled TP/SL: a much wider signal library, honest DISC-only selection.

TP and SL are multiples of the previous day's ATR(14): TP 0.08-0.5 ATR, SL 0.08-3 ATR (the atr50 run of build.py,
level x ATR/50). Results are measured in ATR units per trade (after 0.5 point cost) so that 2009 and 2025 weigh
the same.

Rules are fixed before looking at results (all thresholds in ATR):
  intraday  D30/U30 (0.1, 0.2, 0.3), D60/U60 (0.15, 0.3, 0.5), D120/U120 (0.2, 0.4, 0.6) = move of the last 30/60/120 min
            SD/SU (0.3, 0.6, 1.0) = move since the globex open (18:00), GD/GU (0.3, 0.6, 1.0) = vs previous RTH close
            BPDL / APDH = entry price below the previous day's low / above its high
            each also with the regime filter _B (above MA200) and _R (below MA200)
  daily     PD/PU (0.5, 1.0) = previous day's close-to-close move, RSI2<10 / RSI2>90, IBS<0.2 / IBS>0.8,
            DN3 / UP3 = 3 down / up closes, LO5 / HI5 = close at a 5-day low / high, VH / VL = 20-day vol rank
            >0.8 / <0.2, DOW0..4, BASE
Periods: DISC 2008-2017, VAL 2018-2021, OOS 2022-2026.
Output: /tmp/claude-0/data/atr_grid.parquet (aggregates) and out/atr_*.csv.
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
from irr_engine import TPS, SLS, COST, load_1m  # noqa: E402

DATA = "/tmp/claude-0/data"
OUT = os.path.join(HERE, "out")
INT = 2**31 - 1
PER = ("DISC", "VAL", "OOS")


def label(m):
    t = 18 * 60 + int(m); return f"{t // 60 % 24:02d}:{t % 60:02d}"


def features():
    """extra entry features: 120-min move, move since globex open, distance to previous day's low/high, daily state"""
    import features as F
    E = pd.read_parquet(os.path.join(DATA, "irr_entries.parquet"))
    X = load_1m()
    gday = X.gday.astype("datetime64[D]")
    absmin = (gday.astype(np.int64) * 1440 - 360 + X.gmin).astype(np.int64)
    ei = E.i.to_numpy()

    def prev_move(mins):
        j = np.searchsorted(absmin, absmin[ei] - mins)
        jj = np.minimum(j, len(absmin) - 1)
        good = absmin[jj] == absmin[ei] - mins
        return np.where(good, X.o[ei] - X.o[jj], np.nan)
    E["m120"] = prev_move(120)
    days, first = np.unique(gday, return_index=True)
    d = np.searchsorted(days, gday[ei])
    E["sess"] = X.o[ei] - X.o[first[d]]
    T = F.load()["T"]
    idx = pd.to_datetime(E.gday)
    P = T.shift()                                   # everything known before the session starts
    g = lambda c: P[c].reindex(idx).to_numpy()
    E["pdl"] = X.o[ei] - g("L"); E["pdh"] = X.o[ei] - g("H")
    E["pret"] = (T.C - T.C.shift()).shift().reindex(idx).to_numpy()
    E["rsi2"] = g("rsi2"); E["clv"] = g("clv"); E["rvr"] = g("rv_rank")
    down = (T.C < T.C.shift()).astype(int); up = (T.C > T.C.shift()).astype(int)
    E["dn3"] = (down.rolling(3).sum() == 3).shift().reindex(idx).to_numpy()
    E["up3"] = (up.rolling(3).sum() == 3).shift().reindex(idx).to_numpy()
    E["lo5"] = (T.C <= T.lo5).shift().reindex(idx).to_numpy()
    E["hi5"] = (T.C >= T.hi5).shift().reindex(idx).to_numpy()
    E["per"] = np.where(E.year <= 2017, "DISC", np.where(E.year <= 2021, "VAL", "OOS"))
    return E


def rules(E):
    a = E.atr.to_numpy()
    bull = E.bull.fillna(False).to_numpy().astype(bool)
    f = lambda c: np.nan_to_num(E[c].to_numpy(dtype=float) / a, nan=0.0)
    m30, m60, m120, sess, gap = f("m30"), f("m60"), f("m120"), f("sess"), f("gap_prev_close")
    intr = {}
    for x in (0.1, 0.2, 0.3):
        intr[f"D30_{x}"] = m30 <= -x; intr[f"U30_{x}"] = m30 >= x
    for x in (0.15, 0.3, 0.5):
        intr[f"D60_{x}"] = m60 <= -x; intr[f"U60_{x}"] = m60 >= x
    for x in (0.2, 0.4, 0.6):
        intr[f"D120_{x}"] = m120 <= -x; intr[f"U120_{x}"] = m120 >= x
    for x in (0.3, 0.6, 1.0):
        intr[f"SD_{x}"] = sess <= -x; intr[f"SU_{x}"] = sess >= x
        intr[f"GD_{x}"] = gap <= -x; intr[f"GU_{x}"] = gap >= x
    intr["BPDL"] = E.pdl.to_numpy() < 0; intr["APDH"] = E.pdh.to_numpy() > 0
    R = {"BASE": np.ones(len(E), bool)}
    for k, v in intr.items():
        R[k] = v; R[k + "_B"] = v & bull; R[k + "_R"] = v & ~bull
    pret = f("pret")
    for x in (0.5, 1.0):
        R[f"PD_{x}"] = pret <= -x; R[f"PU_{x}"] = pret >= x
    R["RSI2_10"] = E.rsi2.to_numpy() < 10; R["RSI2_90"] = E.rsi2.to_numpy() > 90
    R["IBS_20"] = E.clv.to_numpy() < 0.2; R["IBS_80"] = E.clv.to_numpy() > 0.8
    for c in ("dn3", "up3", "lo5", "hi5"):
        R[c.upper()] = E[c].fillna(False).to_numpy().astype(bool)
    R["VH"] = E.rvr.to_numpy() > 0.8; R["VL"] = E.rvr.to_numpy() < 0.2
    for k in range(5):
        R[f"DOW{k}"] = E.dow.to_numpy() == k
    return R


def main():
    t0 = time.time()
    E = features()
    E.to_parquet(os.path.join(DATA, "atr_entries.parquet"))
    R = rules(E)
    names = list(R)
    slots = np.unique(E.slot.to_numpy()); ns = len(slots)
    slot_ix = np.searchsorted(slots, E.slot.to_numpy())
    per_ix = pd.Series(E.per).map({"DISC": 0, "VAL": 1, "OOS": 2}).to_numpy()
    sel = np.concatenate([np.flatnonzero(R[r]) for r in names])
    rid = np.concatenate([np.full(int(R[r].sum()), j) for j, r in enumerate(names)])
    key = (rid * ns + slot_ix[sel]) * 3 + per_ix[sel]
    K = len(names) * ns * 3
    print("rules", len(names), "rows", len(sel), round(time.time() - t0), "s", flush=True)
    Z = np.load(os.path.join(DATA, "irr_atr50.npz"))
    atr = E.atr.to_numpy()[sel]; sc = atr / 50.0
    out = []
    for side in ("L", "S"):
        for hz in ("eod", "end5"):
            TT = Z[f"tp_{side}_{hz}"][sel]; SS = Z[f"sl_{side}_{hz}"][sel]; CP = Z[f"cp_{side}_{hz}"][sel]
            for it, tp in enumerate(TPS):
                a = TT[:, it]
                for js, sl in enumerate(SLS):
                    b = SS[:, js]
                    win = a < b; loss = (b <= a) & (b < INT)
                    p = (np.where(win, tp * sc, np.where(loss, -sl * sc, CP)) - COST) / atr     # ATR units
                    n = np.bincount(key, minlength=K); s = np.bincount(key, p, K); s2 = np.bincount(key, p * p, K)
                    w = np.bincount(key, win, K); l = np.bincount(key, loss, K)
                    out.append((side, hz, tp, sl, n, s, s2, w, l))
            print(side, hz, round(time.time() - t0), "s", flush=True)
    # assemble
    rows = []
    rr, ss_ = np.divmod(np.arange(len(names) * ns), ns)
    for side, hz, tp, sl, n, s, s2, w, l in out:
        df = pd.DataFrame({"rule": np.array(names)[rr], "slot": slots[ss_]})
        df["side"] = side; df["hz"] = hz; df["tp"] = tp / 50; df["sl"] = sl / 50
        for p_i, p in enumerate(PER):
            df[f"n_{p}"] = n[p_i::3]; df[f"s_{p}"] = s[p_i::3]; df[f"s2_{p}"] = s2[p_i::3]
            df[f"w_{p}"] = w[p_i::3]; df[f"l_{p}"] = l[p_i::3]
        rows.append(df[df.n_DISC + df.n_VAL + df.n_OOS > 0])
    G = pd.concat(rows, ignore_index=True)
    G.to_parquet(os.path.join(DATA, "atr_grid.parquet"))
    print("grid", len(G), round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
