"""SWING ALPHA signals SW01-SW04, combined hypotheses H1-H5 and benchmarks.

Each signal is a boolean mask over the daily table, evaluated at the RTH close of day t using only
data available then. Every rule is defined once for a direction d (+1 long, -1 short) and mirrored,
so long and short versions are always the same idea.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from features import load


def table():
    T = load()["T"].copy()
    T["flow_ok"] = T.index >= "2010-12-27"           # bid/ask volume only exists from this date
    T["year"] = T.index.year
    T["regime"], T["reg_age"] = regimes(T)
    return T


# ---------------------------------------------------------------- SW04 regime classification
REG = ["Bull", "Bear", "Balance", "Transition"]


def regimes(T):
    """Bull / Bear: price, EMA stack, monthly VWAP and its slope all agree and the move is efficient
    (TE10 >= 0.25). Balance: TE10 < 0.20 (rotation). Everything else = Transition (mixed signals)."""
    votes = (np.sign(T.C - T.ema50) + np.sign(T.ema20 - T.ema50) + T.BM + np.sign(T.slopeM)).to_numpy()
    te = T.TE10.to_numpy()
    r = np.full(len(T), "Transition", dtype=object)
    r[te < 0.20] = "Balance"
    r[(votes == 4) & (te >= 0.25)] = "Bull"
    r[(votes == -4) & (te >= 0.25)] = "Bear"
    r[np.isnan(te) | T.ema50.isna().to_numpy()] = "NA"
    age = np.ones(len(T), int)
    for i in range(1, len(T)):
        age[i] = age[i - 1] + 1 if r[i] == r[i - 1] else 1
    return r, age


def markov(T, period_mask=None):
    r = T.regime.to_numpy()
    if period_mask is not None:
        r = r[period_mask]
    P = pd.DataFrame(0.0, index=REG, columns=REG)
    for a, b in zip(r[:-1], r[1:]):
        if a in REG and b in REG:
            P.loc[a, b] += 1
    return P.div(P.sum(axis=1), axis=0)


def semi_markov(T, max_age=30):
    """P(regime continues tomorrow | regime, age) and expected remaining duration by age."""
    r = T.regime.to_numpy(); age = T.reg_age.to_numpy()
    rows = []
    # run lengths
    runs = []
    s = 0
    for i in range(1, len(r) + 1):
        if i == len(r) or r[i] != r[s]:
            runs.append((r[s], i - s)); s = i
    runs = pd.DataFrame(runs, columns=["regime", "len"])
    for g in REG:
        L = runs[runs.regime == g].len.to_numpy()
        for a in range(1, max_age + 1):
            alive = L[L >= a]
            if len(alive) < 10:
                continue
            rows.append(dict(regime=g, age=a, n=len(alive), p_continue=(alive > a).mean(), exp_remaining=(alive - a).mean()))
    return pd.DataFrame(rows), runs


# ---------------------------------------------------------------- signals
def _first_after_gap(x, gap=3):
    """True where x is True and x was False for at least `gap` days before."""
    x = np.asarray(x, bool)
    out = np.zeros(len(x), bool)
    off = gap
    for i in range(len(x)):
        if x[i]:
            out[i] = off >= gap
            off = 0
        else:
            off += 1
    return out


def build_signals(T):
    """returns list of (family, name, side, mask)"""
    S = []
    sh = lambda s, k=1: s.shift(k)
    vol_hi = T.vol > 1.2 * T.vol20
    for d in (1, -1):
        D = "L" if d > 0 else "S"
        poc_st = T.poc_up_streak if d > 0 else T.poc_dn_streak
        va_st = T.va_up_streak if d > 0 else T.va_dn_streak
        dlt = (d * T.delta5 > 0) & T.flow_ok
        dlt1 = (d * T.delta > 0) & T.flow_ok
        add = lambda fam, nm, m: S.append((fam, nm, d, np.asarray(m.fillna(False) if hasattr(m, "fillna") else m, bool)))

        # SW01 value migration ------------------------------------------------
        A = poc_st >= 2
        C = (poc_st >= 2) & (va_st >= 2)
        add("SW01", "A · POC roste 2 dny", A)
        add("SW01", "B · POC roste 3 dny", poc_st >= 3)
        add("SW01", "C · POC + střed VA 2 dny", C)
        add("SW01", "D · C + nad týdenní VWAP", C & (d * T.BW > 0))
        mig_prev = sh(C).fillna(False).astype(bool)
        add("SW01", "E · migrace + pullback", mig_prev & (d * (T.C - sh(T.C)) < 0) & (d * (T.C - sh(T.POC)) > 0))
        add("SW01", "F · C + delta 5D", C & dlt)
        for th in (0.10, 0.25, 0.50):
            add("SW01", f"VM ≥ {th:.2f} ATR", d * T.VM >= th)
        vm3 = T.VM.rolling(3).sum()
        add("SW01", "VM 3D ≥ 0.50 ATR", d * vm3 >= 0.5)
        add("BENCH", "momentum 5D", d * (T.C - sh(T.C, 5)) > 0)
        add("BENCH", "momentum 20D", d * (T.C - sh(T.C, 20)) > 0)

        # SW02 VWAP MTF alignment -----------------------------------------------
        al = (d * T.BD > 0) & (d * T.BW > 0) & (d * T.BM > 0)
        add("SW02", "V1 · D/W/M zarovnáno", al)
        V2 = al & (d * T.slopeW > 0)
        add("SW02", "V2 · V1 + sklon W", V2)
        add("SW02", "V3 · V2 + sklon M", V2 & (d * T.slopeM > 0))
        add("SW02", "V4 · V1 + delta 5D", al & dlt)
        add("SW02", "V5 · první zarovnání po ≥3 dnech", pd.Series(_first_after_gap(al.to_numpy(), 3), index=T.index))
        touchW = (d * (T.L - T.vwapW) <= 0) if d > 0 else (d * (T.H - T.vwapW) <= 0)
        add("SW02", "V6 · pullback na týdenní VWAP", (d * T.BM > 0) & (d * T.slopeW > 0) & touchW & (d * T.BW > 0))
        add("SW02", "V7 · V1 + migrace POC", al & (d * T.dPOC > 0) & (d * T.dVA > 0))
        add("BENCH", "jen denní VWAP", d * T.BD > 0)
        add("BENCH", "jen týdenní VWAP", d * T.BW > 0)
        # score 0-100: MM25 HF25 Daily15 delta10 MP15 vol/regime10
        score = (12.5 * (d * T.BM > 0) + 12.5 * (d * T.slopeM > 0) + 12.5 * (d * T.BW > 0) + 12.5 * (d * T.slopeW > 0)
                 + 15 * (d * T.BD > 0) + 10 * dlt + 7.5 * (d * T.dPOC > 0) + 7.5 * (d * T.dVA > 0) + 10 * (T.rv_rank < 0.8))
        T[f"score_{D}"] = score
        for lo, hi in ((50, 60), (60, 70), (70, 80), (80, 90), (90, 101)):
            add("SW02", f"skóre {lo}–{min(hi, 100) if hi < 101 else 100}", (score >= lo) & (score < hi))

        # SW03 composite breakout (composite locked at t-1) -------------------------
        cl = sh(T.comp_len)
        edge = sh(T.cVAH) if d > 0 else sh(T.cVAL)
        ext = sh(T.cHigh) if d > 0 else sh(T.cLow)
        has = cl >= 2
        CB1 = has & (d * (T.C - edge) > 0)
        add("SW03", "CB1 · close za VAH/VAL kompozitu", CB1)
        add("SW03", "CB2 · close za High/Low kompozitu", has & (d * (T.C - ext) > 0))
        add("SW03", "CB4 · CB1 + objem > 1.2× průměr", CB1 & vol_hi)
        add("SW03", "CB5 · CB1 + delta dne", CB1 & dlt1)
        add("SW03", "CB6 · CB1 + směr týdenního VWAP", CB1 & (d * T.slopeW > 0))
        add("SW03", "CB8 · délka 2–3 dny", CB1 & (cl <= 3))
        add("SW03", "CB8 · délka 4 dny", CB1 & (cl == 4))
        add("SW03", "CB8 · délka 5+ dní", CB1 & (cl >= 5))
        # CB3 retest: breakout within the last 1-3 days, today trades back to the level and closes beyond
        lvl = np.full(len(T), np.nan); age = np.full(len(T), 99)
        cb1 = CB1.to_numpy(); e_ = edge.to_numpy()
        for i in range(len(T)):
            if cb1[i]:
                lvl[i] = e_[i]; age[i] = 0
            elif i > 0:
                lvl[i] = lvl[i - 1]; age[i] = age[i - 1] + 1
        lvl_prev = pd.Series(lvl, index=T.index).shift(); age_prev = pd.Series(age, index=T.index).shift() + 1
        touch = (T.L <= lvl_prev) if d > 0 else (T.H >= lvl_prev)
        add("SW03", "CB3 · retest prolomené hrany", (age_prev <= 3) & (age_prev >= 1) & ~CB1 & touch & (d * (T.C - lvl_prev) > 0))
        # CB7 failed breakout in the opposite direction -> trade back towards / through the POC
        edge_o = sh(T.cVAL) if d > 0 else sh(T.cVAH)
        edge_o2 = sh(T.cVAL, 2) if d > 0 else sh(T.cVAH, 2)
        failed = (sh(T.comp_len, 2) >= 2) & (-d * (sh(T.C) - edge_o2) > 0) & (d * (T.C - edge_o2) > 0)
        add("SW03", "CB7 · failed breakout opačným směrem", failed)
        add("BENCH", "Donchian 5D", d * (T.C - (sh(T.hi5) if d > 0 else sh(T.lo5))) > 0)
        add("BENCH", "Donchian 20D", d * (T.C - (sh(T.hi20) if d > 0 else sh(T.lo20))) > 0)
        add("BENCH", "Donchian 55D", d * (T.C - (sh(T.hi55) if d > 0 else sh(T.lo55))) > 0)

        # SW04 regime persistence ---------------------------------------------------
        rg = "Bull" if d > 0 else "Bear"
        inr = pd.Series(T.regime == rg, index=T.index)
        add("SW04", f"režim {rg} (vše)", inr)
        for a0, a1 in ((1, 2), (3, 5), (6, 10), (11, 20), (21, 999)):
            add("SW04", f"{rg} stáří {a0}–{a1 if a1 < 999 else '∞'}", inr & (T.reg_age >= a0) & (T.reg_age <= a1))
        add("SW04", f"Balance → {rg} (1. den)", inr & (T.reg_age == 1) & (sh(T.regime) == "Balance"))
        add("SW04", f"Transition → {rg} (1. den)", inr & (T.reg_age == 1) & (sh(T.regime) == "Transition"))
        add("SW04", f"{rg} + HV", inr & (T.rv_rank > 0.8))
        add("SW04", f"{rg} bez HV", inr & (T.rv_rank <= 0.8))
        add("BENCH", "EMA20>EMA50 + ADX>25", (d * (T.ema20 - T.ema50) > 0) & (T.adx14 > 25))
        add("BENCH", "nad/pod MA200", d * (T.C - T.ma200) > 0)

        # combined hypotheses ------------------------------------------------------
        add("H", "H1 · zarovnání + migrace + pullback", V2 & (d * sh(T.dVA) > 0) & (d * (T.C - sh(T.C)) < 0))
        accept = sh(CB1).fillna(False).astype(bool) & (d * (T.C - sh(edge)) > 0)
        add("H", "H2 · balance → breakout → akceptace (2. close)", accept)
        add("H", f"H3 · {rg} stáří 3–10", inr & (T.reg_age >= 3) & (T.reg_age <= 10))
        add("H", "H4 · failed breakout + Transition", failed & (T.regime == "Transition"))
        add("H", "H5 · hodnota předbíhá cenu", (d * T.VM >= 0.25) & (d * T.ret <= 0))

        # references ---------------------------------------------------------------
        add("REF", "RSI(2) extrém (reverze)", (T.rsi2 < 10) if d > 0 else (T.rsi2 > 90))
        add("REF", "každý den", pd.Series(True, index=T.index))
    return S
