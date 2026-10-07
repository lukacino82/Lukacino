"""The three prop-firm strategies from the Mattia (SQR Capital) interview, ported to ES.

S1 Vault Break      30-min, long: close above midnight-CT open + 30 % of ATR15 and above VWAP,
                    signals 10:00-14:30 CT, up to 3 trades/session, TP/SL fixed, exit 14:30 CT.
S2 VWAP Pullback    1-min, long: after a close above the 08:30-09:00 CT opening-range high, price
                    touches VWAP, closes back above it, ADX(14) > 20 and not rising.
                    TP = 5-bar high, SL = 20-bar low, exit 15:55.
S3 Overnight Bias   15-min, long/short: RTH open in the top/bottom third of the 23:00-08:30 CT
                    range sets the bias; close beyond the first 15-min range with ADX(14) > 20.
                    SL = 0.3 x ATR15, TP = 3 x SL, exit 14:30 CT, one trade/day.
NQ dollar exits of S1 (TP $800 = 40 NQ pts, SL $1500 = 75 NQ pts) are translated to ES as
fractions of ATR15 (NQ 2023-26 daily ATR ~ 300 pts -> TP 0.13 ATR, SL 0.25 ATR).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from base import Bars, period, resample_day, run_exit, wilder_adx

ET = lambda hh, mm=0: hh * 60 + mm


def vwap_from(B, s, e):
    tp = (B.h[s:e] + B.l[s:e] + B.c[s:e]) / 3
    v = np.maximum(B.v[s:e], 1e-9)
    return np.cumsum(tp * v) / np.cumsum(v)


def s1_vault_break(B: Bars, k=0.30, tp_atr=0.13, sl_atr=0.25, tp_pts=None, sl_pts=None, max_trades=3,
                   sig_from=ET(11), sig_to=ET(15), exit_at=ET(15, 30), use_vwap=True):
    rows = []
    D = B.D
    for i, day in enumerate(B.days):
        if day not in D.index or not np.isfinite(D.at[day, "atr15"]):
            continue
        atr = D.at[day, "atr15"]
        s, e = B.window(i, ET(1), exit_at)
        if e - s < 200:
            continue
        noise = B.o[s] + k * atr
        vw = vwap_from(B, s, e)
        bars = resample_day(B, s, e, 30)
        tp_o = tp_pts if tp_pts is not None else tp_atr * atr
        sl_o = sl_pts if sl_pts is not None else sl_atr * atr
        busy_until, n = -1, 0
        for t0, o, h, l, c, v, nxt in bars:
            close_t = t0 + 30
            nxt = int(nxt)
            if close_t < sig_from or close_t > sig_to or nxt >= e or nxt <= busy_until:
                continue
            if c > noise and (not use_vwap or c > vw[nxt - 1 - s]):
                ent, ex, xi, code = run_exit(B.o, B.h, B.l, B.c, nxt, e, 1, B.o[nxt] + tp_o, B.o[nxt] - sl_o)
                rows.append((day, 1, ent, ex, ex - ent, code))
                busy_until, n = xi, n + 1
                if n >= max_trades:
                    break
    return frame(rows)


def s2_vwap_pullback(B: Bars, adx1, adx_min=20.0, exit_at=ET(15, 55), anchor=ET(1), tp_n=5, sl_n=20):
    rows = []
    for i, day in enumerate(B.days):
        s, e = B.window(i, anchor, exit_at)
        if e - s < 300:
            continue
        rs, re_ = B.window(i, ET(9, 30), ET(10))
        if re_ - rs < 20:
            continue
        orh = B.h[rs:re_].max()
        vw = vwap_from(B, s, e)
        armed = touched = False
        for j in range(re_, e - 1):
            if not armed:
                armed = B.c[j] > orh
                continue
            if B.l[j] <= vw[j - s]:
                touched = True
            if touched and B.c[j] > vw[j - s] and adx1[j] > adx_min and adx1[j] <= adx1[j - 1]:
                tp = B.h[j - tp_n + 1:j + 1].max()
                sl = B.l[j - sl_n + 1:j + 1].min()
                if tp <= B.o[j + 1]:
                    tp = B.o[j + 1] + 0.25
                ent, ex, xi, code = run_exit(B.o, B.h, B.l, B.c, j + 1, e, 1, tp, sl)
                rows.append((day, 1, ent, ex, ex - ent, code))
                break
    return frame(rows)


def s3_overnight_bias(B: Bars, adx15, idx15, k_sl=0.30, rr=3.0, adx_min=20.0, exit_at=ET(15, 30), third=1 / 3,
                      sides=(1, -1)):
    """adx15 / idx15: ADX of the continuous 15-min series and the raw index where each 15-min bar ends."""
    rows = []
    D = B.D
    end15 = idx15  # raw index of first 1-min bar after each 15-min bar
    for i, day in enumerate(B.days):
        if day not in D.index or not np.isfinite(D.at[day, "atr15"]):
            continue
        atr = D.at[day, "atr15"]
        os_, oe = B.window(i, ET(0), ET(9, 30))
        rs, re_ = B.window(i, ET(9, 30), ET(9, 45))
        s, e = B.window(i, ET(9, 30), exit_at)
        if oe - os_ < 200 or re_ - rs < 10 or e - s < 100:
            continue
        onh, onl = B.h[os_:oe].max(), B.l[os_:oe].min()
        pos = (B.o[rs] - onl) / max(onh - onl, 0.25)
        bias = 1 if pos >= 1 - third else (-1 if pos <= third else 0)
        if bias == 0 or bias not in sides:
            continue
        orh, orl = B.h[rs:re_].max(), B.l[rs:re_].min()
        bars = resample_day(B, re_, e, 15)
        for t0, o, h, l, c, v, nxt in bars:
            nxt = int(nxt)
            if nxt >= e:
                break
            k = np.searchsorted(end15, nxt)
            if k >= len(end15) or end15[k] != nxt:
                continue
            brk = c > orh if bias > 0 else c < orl
            if brk and adx15[k] > adx_min:
                ent = B.o[nxt]
                sl_o = k_sl * atr
                ent, ex, xi, code = run_exit(B.o, B.h, B.l, B.c, nxt, e, bias, ent + bias * rr * sl_o, ent - bias * sl_o)
                rows.append((day, bias, ent, ex, bias * (ex - ent), code))
                break
    return frame(rows)


def frame(rows):
    t = pd.DataFrame(rows, columns=["date", "side", "entry", "exit", "pnl", "code"])
    t["period"] = [period(d) for d in t.date]
    return t


def adx_1min(B):
    return wilder_adx(B.h, B.l, B.c, 14)


def adx_15min(B):
    """Continuous clock-aligned 15-min bars over the whole series."""
    key = (B.ts.astype("datetime64[m]").astype(np.int64) // 15)
    brk = np.r_[0, np.where(np.diff(key) != 0)[0] + 1, len(key)]
    H = np.maximum.reduceat(B.h, brk[:-1]); L = np.minimum.reduceat(B.l, brk[:-1])
    C = B.c[brk[1:] - 1]
    return wilder_adx(H, L, C, 14), brk[1:]
