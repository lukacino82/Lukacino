"""Block 2 - cumulative delta.
A  longs only on days with positive cumulative delta: at 10:00 .. 15:00 ET, CD (from 09:30 and from 18:00) > 0 vs < 0
B  extreme CD: first time in a Globex day the CD crosses +-5k .. +-40k contracts, and normalised thresholds
   (CD / average daily volume of the previous 20 days); continuation vs reversal
C  'flushing': CD runs to a peak >= T, falls back to ~0 (<= 10 % of the peak), then resumes to >= 50 % of the peak
   in the original direction -> trade in that direction; variant with price holding above the day VWAP
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prep as P

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def part_A(f, S):
    rows = []
    mod = f["mod"].to_numpy()
    for hh in (600, 630, 660, 720, 780, 840, 900):
        at = mod == hh
        for col in ("cd_r", "cd_g"):
            cd = f[col].to_numpy()
            for cond, m in (("CD > 0", cd > 0), ("CD < 0", cd < 0), ("vse", np.ones(len(f), bool))):
                for r in S.run(at & m, 1, f"{hh // 60:02d}:{hh % 60:02d} {col} {cond}"):
                    r.update(cas=f"{hh // 60:02d}:{hh % 60:02d}", cd=col, podminka=cond); rows.append(r)
    A = pd.DataFrame(rows)
    A.round(4).to_csv(os.path.join(OUT, "A_cd_kladne_longy.csv"), index=False)
    return A


def part_B(f, S):
    rows = []
    cd = f.cd_g.to_numpy(); gd = f.gday.to_numpy()
    vol_d = f.groupby("gday").V.sum()
    avgv = f.gday.map(vol_d.rolling(20).mean().shift(1)).to_numpy()
    norm = cd / avgv * 100                                     # % of an average day's volume
    for kind, series, levels in (("kontrakty", cd, (5000, 10000, 15000, 20000, 30000, 40000)),
                                 ("% objemu dne", norm, (0.5, 1, 1.5, 2, 3))):
        for lv in levels:
            for sgn in (1, -1):
                m = sgn * series >= lv
                ev = P.first_per_day(m, gd)
                for side, lab in ((sgn, "pokracovani"), (-sgn, "obrat")):
                    for r in S.run(ev, side, f"CD {'+' if sgn > 0 else '-'}{lv:g} {kind} -> {lab}"):
                        r.update(typ=kind, uroven=sgn * lv, sazka=lab); rows.append(r)
    B = pd.DataFrame(rows)
    B.round(4).to_csv(os.path.join(OUT, "B_cd_extremy.csv"), index=False)
    return B


@njit(cache=True)
def flush_events(cd, dpos, price, vwap, T, back, resume, need_price):
    """per day: peak >= T, then |cd| <= back*peak, then cd >= resume*peak again -> event (sign of the run)"""
    n = len(cd); ev = np.zeros(n, np.int8)
    state = 0; peak = 0.0; sgn = 0
    for i in range(n):
        if i == 0 or dpos[i] != dpos[i - 1]:
            state = 0; peak = 0.0; sgn = 0
        c = cd[i]
        if state == 0:
            if c >= T:
                state = 1; sgn = 1; peak = c
            elif c <= -T:
                state = 1; sgn = -1; peak = -c
        elif state == 1:
            if sgn * c > peak:
                peak = sgn * c
            if sgn * c <= back * peak:
                state = 2
        elif state == 2:
            if sgn * c >= resume * peak:
                ok = True
                if need_price:
                    ok = (price[i] - vwap[i]) * sgn > 0
                if ok:
                    ev[i] = sgn
                state = 3
            elif sgn * c < -T:                       # flipped into a real opposite run
                state = 3
    return ev


def part_C(f, S):
    rows = []
    cd = f.cd_g.to_numpy(); price = f.C.to_numpy(); vw = f.vwap_d.to_numpy()
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    for T in (5000, 10000, 15000):
        for back in (0.1, 0.25):
            for need in (False, True):
                ev = flush_events(cd, dpos, price, vw, float(T), back, 0.5, need)
                for sgn in (1, -1):
                    nm = f"flush T{T} zpet<={back:g} {'cena za VWAP' if need else 'bez ceny'} {'long' if sgn > 0 else 'short'}"
                    for r in S.run(ev == sgn, sgn, nm):
                        r.update(T=T, navrat=back, podminka_vwap=need); rows.append(r)
    C = pd.DataFrame(rows)
    C.round(4).to_csv(os.path.join(OUT, "C_cd_flushing.csv"), index=False)
    return C


if __name__ == "__main__":
    f = P.load(); S = P.Study(f)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    cols = ["udalost", "horizont", "n", "zmena_atr", "excess_atr", "t", "p_zisk", "excess_2011_18", "excess_2019_26"]
    A = part_A(f, S); print(A[A.horizont == "close"][cols].round(3).to_string())
    B = part_B(f, S); print(B[B.horizont.isin(["60m", "close"])][cols].round(3).to_string())
    C = part_C(f, S); print(C[C.horizont.isin(["60m", "close"])][cols].round(3).to_string())
