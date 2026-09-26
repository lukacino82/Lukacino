"""Feature matrices (day x 5-minute bucket) and the strategy registry.

Every strategy is long-only, fires at most once per day on the first qualifying
completed 5-minute RTH bucket and is described by
    signal mask (nd x 78), day-level regime mask (for the null model), exits.
Exit `("atr", tp, sl)` = multiples of the prior ATR20, `("pts", tp, sl)` = points.
"""
from __future__ import annotations

import numpy as np

from engine import NBUCKET

LAST_SIGNAL_BUCKET = 71  # last signal bucket ends 15:30


def shift(a, k, fill=np.nan):
    out = np.full_like(a, fill, dtype=float)
    out[:, k:] = a[:, :-k]
    return out


def features(S):
    F = {}
    nd = len(S.dates)
    C, H, L, V, D = S.C5, S.H5, S.L5, S.V5, S.D5
    F["C"], F["L"] = C, L
    col = lambda x: np.repeat(np.asarray(x, float)[:, None], NBUCKET, 1)
    colb = lambda x: np.repeat(np.asarray(x, bool)[:, None], NBUCKET, 1)
    # lower-close streak
    lower = np.zeros_like(C, bool)
    lower[:, 1:] = C[:, 1:] < C[:, :-1]
    st = np.zeros_like(C)
    for j in range(1, NBUCKET):
        st[:, j] = np.where(lower[:, j], st[:, j - 1] + 1, 0)
    F["lc"] = st
    F["ret30"] = C / shift(C, 6) - 1
    F["ret60"] = C / shift(C, 12) - 1
    F["div30"] = (C < shift(C, 6)) & (S.cd > shift(S.cd, 6))
    F["delta"] = D
    F["flip"] = (D > 0) & (shift(D, 1) <= 0)
    F["vwap"], F["vz"] = S.vwap, S.vwap_z
    F["vwap_reclaim"] = (C > S.vwap) & (shift(C, 1) < shift(S.vwap, 1))
    # volume z-score vs the same bucket over the prior 20 sessions
    mu = np.full_like(V, np.nan); sd = mu.copy()
    for i in range(20, nd):
        w = V[i - 20:i]
        mu[i], sd[i] = w.mean(0), w.std(0)
    F["volz"] = (V - mu) / sd
    # levels (raw prices of the traded contract); prior-day levels blocked on roll days
    ok = ~S.roll
    F["pdl"] = col(np.where(ok, S.pdl, np.nan))
    F["val"] = col(np.where(ok, S.val, np.nan))
    F["poc"] = col(np.where(ok, S.poc, np.nan))
    F["onl"] = col(S.onl)
    or15 = np.nanmin(L[:, :3], 1); or30 = np.nanmin(L[:, :6], 1)
    j = np.arange(NBUCKET)[None, :]
    F["or15"] = np.where(j >= 3, col(or15), np.nan)
    F["or30"] = np.where(j >= 6, col(or30), np.nan)
    R = S.R
    F["bull"] = colb(R.bull200.to_numpy())
    F["down2"] = colb(R.down2.to_numpy())
    F["prev_up"] = colb(R.prev_up.to_numpy())
    F["gap"] = col(R.gap.to_numpy())
    F["dd252"] = col(R.dd252_prev.to_numpy())
    F["atr_rank"] = col(R.atr_rank.to_numpy())
    F["atr"] = col(R.atr20.to_numpy())
    off = np.where(ok, S.adj_off, np.nan)
    F["ath_dd"] = (C + col(off)) / col(R.ath.to_numpy()) - 1
    F["j"] = np.broadcast_to(j, C.shape)
    F["minute_end"] = 9 * 60 + 30 + 5 * (F["j"] + 1)
    F["bull_day"] = R.bull200.to_numpy(bool)
    F["all_day"] = np.ones(nd, bool)
    F["ma_ok"] = R.ma200_ok.to_numpy(bool)
    return F


def sweep(F, lvl):
    with np.errstate(invalid="ignore"):
        return (F["L"] < lvl) & (F["C"] > lvl)


def between(F, a, b):
    """signal bucket ends within [a, b] (HHMM)."""
    to = lambda x: (x // 100) * 60 + x % 100
    m = F["minute_end"]
    return (m >= to(a)) & (m <= to(b))


def registry(F):
    """name -> dict(phase, rule, mask, regime, exit)."""
    g = lambda k: np.nan_to_num(F[k], nan=0.0)
    with np.errstate(invalid="ignore"):
        bull, div, flip, C = F["bull"], F["div30"], F["flip"], F["C"]
        S = {}

        def add(name, phase, rule, mask, exit_, regime="bull_day"):
            S[name] = dict(phase=phase, rule=rule, mask=mask & (F["j"] <= 71), exit=exit_, regime=regime)

        # ---------------- Phase 4 (codex_astra_strategy_spec.json)
        for dd in (5, 8, 10, 15, 20):
            add(f"ATH_DD{dd}_PDL_Div", "P4", f"drawdown from ATH <= -{dd}% + PDL sweep/reclaim + delta divergence",
                (F["ath_dd"] <= -dd / 100) & sweep(F, F["pdl"]) & div, ("atr", 0.75, 1.0), "all_day")
        add("DD2_AboveMA200_PDL_Sweep", "P4", "bull200 + prior close <= -2% from 252d high + PDL sweep/reclaim",
            bull & (F["dd252"] <= -0.02) & sweep(F, F["pdl"]), ("atr", 1.0, 1.5))
        for z in (0.75, 1.0):
            add(f"2Down_Bull_VWAPz{z}_Flip", "P4", f"2 prior down days + bull200 + VWAP z<=-{z} + delta flip positive",
                bull & F["down2"] & (F["vz"] <= -z) & flip, ("atr", 0.75, 1.5))
        add("Bull_Gap0.2_PDL_Reclaim", "P4", "bull200 + RTH gap<=-0.2% + PDL sweep/reclaim + positive delta",
            bull & (F["gap"] <= -0.002) & sweep(F, F["pdl"]) & (F["delta"] > 0), ("atr", 0.25, 1.0))
        add("Bull_BelowVAL_BelowPDL_Div", "P4", "bull200 + close below prior VAL and below PDL + delta divergence",
            bull & (C < F["val"]) & (C < F["pdl"]) & div, ("atr", 0.75, 1.0))
        add("Bull_OR30L_SweepReclaim_Div", "P4", "bull200 + OR30-low sweep/reclaim + delta divergence",
            bull & sweep(F, F["or30"]) & div, ("atr", 0.25, 1.0))
        add("Bull_OR15L_SweepReclaim_Div", "P4", "bull200 + OR15-low sweep/reclaim + delta divergence",
            bull & sweep(F, F["or15"]) & div, ("atr", 0.25, 0.5))
        add("OR30L_SweepReclaim_DeltaPos", "P4", "OR30-low sweep/reclaim + positive 5m delta (no regime)",
            sweep(F, F["or30"]) & (F["delta"] > 0), ("atr", 0.5, 1.0), "all_day")
        add("Bull_PDL_Reclaim_POCbelow", "P4", "bull200 + PDL sweep/reclaim + close below prior POC + positive delta",
            bull & sweep(F, F["pdl"]) & (C < F["poc"]) & (F["delta"] > 0), ("atr", 0.25, 1.5))
        add("Bull_PDL_SweepReclaim_Div", "P4", "bull200 + PDL sweep/reclaim + delta divergence",
            bull & sweep(F, F["pdl"]) & div, ("atr", 1.0, 1.5))
        add("Bull_ONL_SweepReclaim_Div", "P4", "bull200 + overnight-low sweep/reclaim + delta divergence",
            bull & sweep(F, F["onl"]) & div, ("atr", 1.5, 0.5))
        add("Bull_R30ATR0.5_DeltaDiv", "P4", "bull200 + 30m move <= -0.5 ATR20 + delta divergence",
            bull & ((C - shift(C, 6)) <= -0.5 * F["atr"]) & div, ("atr", 0.75, 0.75))

        # ---------------- Phase 1 (fixed-point exits as published)
        add("P1_Bull_2LC_NegDelta", "P1", "bull200 + >=2 lower 5m closes + negative 5m delta; TP16/SL12 pts",
            bull & (F["lc"] >= 2) & (F["delta"] < 0), ("pts", 16, 12))
        add("P1_Bull_3LC_NegDelta", "P1", "bull200 + >=3 lower 5m closes + negative 5m delta; TP12/SL12 pts",
            bull & (F["lc"] >= 3) & (F["delta"] < 0), ("pts", 12, 12))
        add("P1_Close_Below_PDL", "P1", "5m close below prior-day low; TP24/SL30 pts",
            C < F["pdl"], ("pts", 24, 30), "all_day")
        add("P1_Failed_PDL_Breakdown", "P1", "PDL sweep/reclaim; TP24/SL30 pts",
            sweep(F, F["pdl"]), ("pts", 24, 30), "all_day")
        add("P1_VWAP_Reclaim", "P1", "5m close back above session VWAP; TP20/SL40 pts",
            F["vwap_reclaim"] & (F["j"] >= 2), ("pts", 20, 40), "all_day")
        add("P1_Below_Prior_VAL", "P1", "5m close below prior-day VAL; TP24/SL30 pts",
            C < F["val"], ("pts", 24, 30), "all_day")

        # ---------------- Phase 2 (multi-factor shortlist, ATR exits 1.0 / 1.25)
        morning = between(F, 935, 1100)
        add("Q_Morning_VWAP_Volume", "P2", "09:30-11:00, 30m ret <= -0.5%, VWAP z < -1, volume z > 1",
            morning & (F["ret30"] <= -0.005) & (F["vz"] < -1) & (F["volz"] > 1), ("atr", 1.0, 1.25), "all_day")
        add("Q_Morning_POC_VWAP", "P2", "09:30-11:00, 30m ret <= -0.5%, below VWAP and below prior POC",
            morning & (F["ret30"] <= -0.005) & (C < F["vwap"]) & (C < F["poc"]), ("atr", 1.0, 1.25), "all_day")
        add("Q_PDL_Div_HighATR", "P2", "below PDL + delta divergence + ATR20 in top 40% + prior day up",
            (C < F["pdl"]) & div & (F["atr_rank"] >= 0.6) & F["prev_up"], ("atr", 1.0, 1.25), "all_day")
        add("Q_Bull_10_12_DeltaDiv", "P2", "bull200, 10:00-12:00, 60m ret <= -0.5%, delta divergence",
            bull & between(F, 1000, 1200) & (F["ret60"] <= -0.005) & div, ("atr", 1.0, 1.25))
        add("Q_VWAP_PDL_Reclaim", "P2", "prior day down + PDL reclaim today + VWAP reclaim + delta flip",
            ~F["prev_up"] & (np.maximum.accumulate(np.nan_to_num(sweep(F, F["pdl"]).astype(float)), 1) > 0)
            & F["vwap_reclaim"] & flip, ("atr", 1.0, 1.25), "all_day")
        add("Q_DeepGap_VWAP_DeltaDiv", "P2", "RTH gap <= -0.5% + below VWAP + delta divergence",
            (F["gap"] <= -0.005) & (C < F["vwap"]) & div, ("atr", 1.0, 1.25), "all_day")
    for v in S.values():
        v["mask"] = np.nan_to_num(v["mask"]).astype(bool)
    return S
