"""Block 3 - VWAP.
A  fade of +-2 SD of the daily VWAP (Globex and RTH VWAP), first touch from inside during RTH: TP = VWAP or 1 SD,
   SL = 1 SD beyond the band; also +-1 / +-3 SD; split by balance (flat VWAP over 60 min, open inside yesterday's range)
B  VWAP cross and retest: price closes across the daily VWAP, stays on that side >= 15 min, then returns to VWAP
   (within 0.1 SD) within 120 min -> trade away from VWAP (TP 1 SD, SL 0.5 SD), long and short
C  framework: the daily retest (B) and the 2 SD fade (A) split by the position vs the weekly / monthly VWAP and the
   slope of the monthly VWAP
D  daily: position at the RTH close in weekly / monthly VWAP bands (z) -> excess return 1 / 5 / 10 days ahead
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prep as P
from trade import summarize

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def day_end(f):
    """last RTH bar (15:59) of the same Globex day for every bar"""
    idx = np.arange(len(f)); mod = f["mod"].to_numpy()
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    cb = pd.Series(np.where((mod >= 570) & (mod <= 959), idx, -1)).groupby(dpos).max().to_numpy()
    return cb[dpos], dpos


def context(f):
    C = f.C.to_numpy()
    g = f.groupby("gday").agg(H=("H", "max"), L=("L", "min"))
    ph = f.gday.map(g.H.shift(1)).to_numpy(); pl = f.gday.map(g.L.shift(1)).to_numpy()
    op = f.gday.map(f[f.rth].groupby("gday").O.first()).to_numpy()
    inside_open = (op <= ph) & (op >= pl)
    vw = f.vwap_d.to_numpy(); sd = f.sd_d.to_numpy()
    flat = np.abs(vw - np.r_[np.full(60, np.nan), vw[:-60]]) < 0.25 * sd
    above_w = C > f.vwap_w.to_numpy(); above_m = C > f.vwap_m.to_numpy()
    vm = f.vwap_m.to_numpy()
    mslope = vm - np.r_[np.full(1380, np.nan), vm[:-1380]]          # ~1 trading day of minutes
    return dict(balance_open=inside_open, flat=flat, above_w=above_w, above_m=above_m, m_up=mslope > 0)


def part_A(f, end, ctx):
    rows = []
    C = f.C.to_numpy(); H = f.H.to_numpy(); L = f.L.to_numpy()
    rth = f.rth.to_numpy() & (f["mod"].to_numpy() <= 930)
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    for vwname, vcol, scol in (("denni VWAP (18:00)", "vwap_d", "sd_d"), ("RTH VWAP (9:30)", "vwap_r", "sd_r")):
        vw = f[vcol].to_numpy(); sd = f[scol].to_numpy()
        for k in (1, 2, 3):
            for side in (-1, 1):                                    # -1 = short at +k SD, +1 = long at -k SD
                band = vw - side * k * sd
                touch = (H >= band) if side == -1 else (L <= band)
                prev_in = np.r_[False, ((C < band) if side == -1 else (C > band))[:-1]]
                m = touch & prev_in & rth & (sd > 0.5)
                first = pd.Series(m).groupby(dpos).cumsum().to_numpy() == 1
                ev = np.flatnonzero(m & first)
                e = C[ev]
                for tpname, tp in (("TP VWAP", vw[ev]), ("TP 1 SD", vw[ev] - side * max(k - 1, 0.5) * sd[ev])):
                    sl = e - side * 1.0 * sd[ev]
                    for cname, cm in (("vse", np.ones(len(ev), bool)), ("balance: plochy VWAP", ctx["flat"][ev]),
                                      ("trend: VWAP se hybe", ~ctx["flat"][ev]),
                                      ("balance: open v range vcerejska", ctx["balance_open"][ev]),
                                      ("open mimo range vcerejska", ~ctx["balance_open"][ev])):
                        sel = ev[cm]
                        r = summarize(f"fade {'+' if side == -1 else '-'}{k}SD {vwname} {tpname} {cname}", f, sel,
                                      np.full(len(sel), side), tp[cm], sl[cm], end[sel],
                                      dict(vwap=vwname, SD=k, strana="short u +SD" if side == -1 else "long u -SD",
                                           cil=tpname, rezim=cname))
                        if r:
                            rows.append(r)
    A = pd.DataFrame(rows)
    A.round(4).to_csv(os.path.join(OUT, "D_vwap_fade_sd.csv"), index=False)
    return A


@njit(cache=True)
def retest_events(C, H, L, vw, sd, dpos, rth, hold, window, tol):
    """cross: close on the other side of VWAP after being on the first side; must stay >= hold bars;
    then first touch of VWAP +- tol*sd within `window` bars -> event with direction of the cross"""
    n = len(C); ev = np.zeros(n, np.int8)
    side = 0; since = 0; cross_i = -1; armed = 0
    for i in range(1, n):
        if dpos[i] != dpos[i - 1]:
            side = 0; since = 0; armed = 0
        s = 1 if C[i] > vw[i] else -1
        if s != side:
            if side != 0:
                cross_i = i; armed = s
            side = s; since = 0
        else:
            since += 1
        if armed != 0 and rth[i] and since >= hold and i - cross_i <= window:
            if armed == 1 and L[i] <= vw[i] + tol * sd[i] and C[i] > vw[i]:
                ev[i] = 1; armed = 0
            elif armed == -1 and H[i] >= vw[i] - tol * sd[i] and C[i] < vw[i]:
                ev[i] = -1; armed = 0
        if armed != 0 and i - cross_i > window:
            armed = 0
    return ev


def part_B(f, end, ctx):
    rows = []
    C = f.C.to_numpy(); H = f.H.to_numpy(); L = f.L.to_numpy()
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    rth = f.rth.to_numpy() & (f["mod"].to_numpy() <= 930)
    store = {}
    for vwname, vcol, scol in (("denni VWAP (18:00)", "vwap_d", "sd_d"), ("RTH VWAP (9:30)", "vwap_r", "sd_r")):
        vw = np.nan_to_num(f[vcol].to_numpy()); sd = np.nan_to_num(f[scol].to_numpy())
        for hold in (15, 30):
            ev = retest_events(C, H, L, vw, sd, dpos, rth, hold, 120, 0.1)
            store[(vwname, hold)] = ev
            for sgn in (1, -1):
                idx = np.flatnonzero(ev == sgn)
                idx = idx[sd[idx] > 0.5]
                e = C[idx]
                for tpk, slk in ((1.0, 0.5), (1.0, 1.0), (2.0, 1.0)):
                    tp = e + sgn * tpk * sd[idx]; sl = e - sgn * slk * sd[idx]
                    r = summarize(f"retest {vwname} drzeni {hold}m {'long' if sgn > 0 else 'short'} TP{tpk:g}SD SL{slk:g}SD",
                                  f, idx, np.full(len(idx), sgn), tp, sl, end[idx],
                                  dict(vwap=vwname, drzeni=hold, smer="long" if sgn > 0 else "short", TP_SD=tpk, SL_SD=slk))
                    if r:
                        rows.append(r)
    B = pd.DataFrame(rows)
    B.round(4).to_csv(os.path.join(OUT, "E_vwap_retest.csv"), index=False)
    return B, store


def part_C(f, end, ctx, store):
    """framework: retest (daily VWAP, hold 15) and -2SD/+2SD fade split by weekly / monthly context"""
    rows = []
    C = f.C.to_numpy(); sd = f.sd_d.to_numpy()
    ev = store[("denni VWAP (18:00)", 15)]
    combos = {"nad W i M VWAP": ctx["above_w"] & ctx["above_m"], "pod W i M VWAP": ~ctx["above_w"] & ~ctx["above_m"],
              "nad W, pod M": ctx["above_w"] & ~ctx["above_m"], "pod W, nad M": ~ctx["above_w"] & ctx["above_m"],
              "M VWAP roste": ctx["m_up"], "M VWAP klesa": ~ctx["m_up"]}
    for sgn in (1, -1):
        base = np.flatnonzero(ev == sgn)
        base = base[sd[base] > 0.5]
        for cname, cm in combos.items():
            idx = base[cm[base]]
            e = C[idx]
            r = summarize(f"retest denniho VWAP {'long' if sgn > 0 else 'short'} | {cname}", f, idx,
                          np.full(len(idx), sgn), e + sgn * sd[idx], e - sgn * 0.5 * sd[idx], end[idx],
                          dict(setup="retest denniho VWAP", smer="long" if sgn > 0 else "short", kontext=cname))
            if r:
                rows.append(r)
    # 2 SD fade under context
    H = f.H.to_numpy(); L = f.L.to_numpy(); vw = f.vwap_d.to_numpy()
    dpos = np.unique(f.gday.to_numpy(), return_inverse=True)[1]
    rth = f.rth.to_numpy() & (f["mod"].to_numpy() <= 930)
    for side in (1, -1):
        band = vw - side * 2 * sd
        touch = (L <= band) if side == 1 else (H >= band)
        prev_in = np.r_[False, ((C > band) if side == 1 else (C < band))[:-1]]
        m = touch & prev_in & rth & (sd > 0.5)
        idx0 = np.flatnonzero(m & (pd.Series(m).groupby(dpos).cumsum().to_numpy() == 1))
        for cname, cm in combos.items():
            idx = idx0[cm[idx0]]
            e = C[idx]
            r = summarize(f"fade {'-2SD long' if side == 1 else '+2SD short'} | {cname}", f, idx, np.full(len(idx), side),
                          vw[idx], e - side * sd[idx], end[idx],
                          dict(setup="fade 2SD denniho VWAP", smer="long" if side == 1 else "short", kontext=cname))
            if r:
                rows.append(r)
    R = pd.DataFrame(rows)
    R.round(4).to_csv(os.path.join(OUT, "F_vwap_framework.csv"), index=False)
    return R


def part_D(f):
    """end-of-day position in weekly / monthly VWAP bands -> excess return over the next 1 / 5 / 10 days (ATR)"""
    r = f[f["mod"] == 959].copy()
    r = r.set_index("gday")
    rows = []
    for k in (1, 5, 10):
        r[f"f{k}"] = (r.C.shift(-k) - r.C) / r.atr
        r[f"x{k}"] = r[f"f{k}"] - r[f"f{k}"].mean()
    for name, vc, sc in (("tydenni", "vwap_w", "sd_w"), ("mesicni", "vwap_m", "sd_m")):
        z = (r.C - r[vc]) / r[sc].replace(0, np.nan)
        b = pd.cut(z, [-np.inf, -2, -1, 0, 1, 2, np.inf], labels=["< -2SD", "-2..-1", "-1..0", "0..+1", "+1..+2", "> +2SD"])
        for lab, g in r.groupby(b, observed=True):
            row = dict(vwap=name, pasmo=str(lab), dnu=len(g))
            for k in (1, 5, 10):
                x = g[f"x{k}"].dropna()
                row[f"excess_{k}d_atr"] = x.mean(); row[f"t_{k}d"] = x.mean() / x.std() * np.sqrt(len(x) / k)
                row[f"p_rust_{k}d"] = (g[f"f{k}"].dropna() > 0).mean()
            rows.append(row)
    D = pd.DataFrame(rows)
    D.round(4).to_csv(os.path.join(OUT, "G_vwap_tyden_mesic_pasma.csv"), index=False)
    return D


if __name__ == "__main__":
    f = P.load()
    end, _ = day_end(f)
    ctx = context(f)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    cols = ["test", "n", "win", "nahodna_win", "tp_body", "sl_body", "hrube_b", "cisty_b", "t", "cisty_2011_18", "cisty_2019_26"]
    A = part_A(f, end, ctx); print(A[cols].round(3).to_string(), flush=True)
    B, store = part_B(f, end, ctx); print(B[cols].round(3).to_string(), flush=True)
    C = part_C(f, end, ctx, store); print(C[cols].round(3).to_string(), flush=True)
    D = part_D(f); print(D.round(3).to_string())
