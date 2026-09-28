"""
Correction strategies from CORRECTION_ALPHA_BLUEPRINT, as testable setups.

Naming: <ID>_<short name>. IDs follow the blueprint so every rule is traceable to its hypothesis.
Every strategy is a layered rule - weakness, location, exhaustion, trigger - and never a bare
oscillator reading. E-family (real VAP) is approximated from 1-minute volume-at-price profiles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def correction_setups(d: pd.DataFrame):
    c, h, l, o = d.close, d.high, d.low, d.open
    atr = d.atr20
    out = []
    bull = (c > d.sma200) & (d.sma200 > d.sma200.shift(20))      # price above a rising MA200
    bull_soft = c > d.sma200
    bear = (c < d.sma200) & (d.sma200 < d.sma200.shift(20))

    def add(name, lsig, ssig=None, emode=0, llim=None, slim=None):
        f = lambda x: np.asarray(pd.Series(x).fillna(False).astype(bool)) if x is not None else None  # noqa: E731
        out.append((name, f(lsig), f(ssig), emode,
                    None if llim is None else np.asarray(llim, float),
                    None if slim is None else np.asarray(slim, float)))

    # ============ A  weakness / losing streaks =========================================
    for k in (2, 3, 4, 5):
        add(f"A01_Down{k}_bull", bull & (d.downdays >= k))
        add(f"A01_Down{k}_any", d.downdays >= k)
    for k in (3, 5, 7):
        for th in (-2.0, -3.0):
            add(f"A02_WStreak{k}<{th}", bull_soft & (d[f"wstreak{k}"] < th))
    for k in (2, 3, 5, 10):
        for p in (0.02, 0.05, 0.10):
            add(f"A03_CumRet{k}p{int(p*100)}", bull_soft & (d[f"cumret{k}_pct"] < p))
    for s in (1.0, 1.5, 2.0, 3.0):
        add(f"A04_Shock{s}ATR", bull_soft & (d.atr_shock > s))
        add(f"A04_Shock2d{s}ATR", bull_soft & (d.atr_shock2 > s))
    add("A05_AccelDown", bull_soft & d.accel_down)
    add("A05_AccelDown_stop", bull_soft & d.accel_down, emode=3, llim=h)   # wait for upside break
    for extra in ("", "_rng", "_vol"):
        cond = d.decel_down & (d.range_shrink if extra == "_rng" else d.vol_shrink if extra == "_vol" else True)
        add(f"A06_Decel{extra}", bull_soft & cond & (d.dd < -0.02))
        add(f"A06_Decel{extra}_ibs", bull_soft & cond & (d.ibs > 0.5) & (d.dd < -0.02))
    for N in (5, 10, 20):
        add(f"A07_FailedBreak{N}", d[f"sweep{N}"])
        add(f"A07_FailedBreak{N}_bull", bull_soft & d[f"sweep{N}"])
        add(f"A07_FailedBreak{N}_stop", d[f"sweep{N}"], emode=3, llim=h)
    add("A08_OutsideRev", d.outside_rev & (d.dd < -0.02))
    add("A08_OutsideRev_bull", bull_soft & d.outside_rev & (d.dd < -0.02))
    for s in (1.0, 2.0):
        add(f"A09_InsideAfter{s}ATR", d.inside_day & (d.atr_shock2 > s), emode=3, llim=h)
    add("A10_HigherLow", bull_soft & d.higher_low & (d.dd < -0.03) & (c > d.sma3))
    add("A10_HigherLow_deep", bull_soft & d.higher_low & (d.dd < -0.05))
    for g in (0.5, 1.0, 1.5):
        add(f"A11_GapDown{g}_recover", (d.gap_atr < -g) & (c > o))
        add(f"A11_GapDown{g}_bull", bull_soft & (d.gap_atr < -g) & (c > o))
    add("A12_LowRetest", d.retest_low & (d.ibs > 0.5))
    add("A12_LowRetest_delta", d.retest_low & (d.eth_delta > d.eth_delta.shift()))

    # ============ B  drawdown anatomy ==================================================
    lad = [(0.02, 0.03), (0.03, 0.05), (0.05, 0.075), (0.075, 0.10), (0.10, 0.15), (0.15, 1.0)]
    for a, b in lad:
        st = (d.dd <= -a) & (d.dd > -b)
        tag = f"{int(a*1000)}"
        add(f"B01_DD{tag}_stab", st & (c > c.shift()))                       # stabilisation trigger
        add(f"B01_DD{tag}_bull", st & bull_soft & (c > c.shift()))
        add(f"B01_DD{tag}_sma3", st & (c > d.sma3))
    for v in (0.002, 0.004, 0.008):                                          # depth per session
        add(f"B02_FastDD{int(v*1000)}", (d.dd_velocity < -v) & (c > c.shift()))
        add(f"B02_FastDD{int(v*1000)}_bull", bull_soft & (d.dd_velocity < -v) & (c > c.shift()))
    add("B02_SlowGrind", (d.dd < -0.04) & (d.days_from_peak > 25) & (c > d.sma10))
    for t in (0.3, 0.6, 1.0):
        add(f"B03_TUW{t}", (d.time_under_water > t) & (c > d.sma3))
    for f_ in (0.25, 0.382, 0.5):
        add(f"B04_Recov{int(f_*100)}", (d.recovery_frac > f_) & (d.recovery_frac.shift() <= f_) & (d.dd < -0.03))
    add("B04_FirstPullbackAfterRecov", (d.recovery_frac > 0.382) & (c < c.shift()) & (d.dd < -0.03) & bull_soft)
    add("B05_VshapeReclaim", (d.days_from_low <= 3) & (d.recovery_frac > 0.382) & (d.dd < -0.03))
    add("B05_Wshape", d.retest_low & (d.days_from_peak > 10) & (c > d.sma3))

    # ============ C  RSI / MA hybrids ==================================================
    for th in (5, 10, 15):
        add(f"C01_RSI2<{th}_bullMA", bull & (d.rsi2 < th))
        add(f"C01_RSI2<{th}_turn", bull_soft & (d.rsi2.shift() < th) & (d.rsi2 > d.rsi2.shift()))
    for p in (0.05, 0.10):
        add(f"C02_CumRSIpct{int(p*100)}", bull_soft & (d.crsi2_2.rolling(504, min_periods=120).rank(pct=True) < p))
    add("C03_RSIdiv", d.ll10 & (d.rsi2 > d.rsi2.shift(5)) & bull_soft)
    add("C03_RSIdiv_trig", d.ll10.shift().fillna(False) & (d.rsi2.shift() > d.rsi2.shift(6)) & (c > h.shift()))
    for m in (10, 20, 50):
        for k in (0.5, 1.0, 1.5, 2.0):
            dist = (c - d[f"sma{m}"]) / atr
            add(f"C04_Dist{m}<-{k}ATR", bull_soft & (dist < -k))
            add(f"C04_Dist{m}<-{k}ATR_up", bull_soft & (dist < -k) & (c > c.shift()))
    stack = (d.sma20 > d.sma50) & (d.sma50 > d.sma200) & (d.sma20 > d.sma20.shift(5))
    add("C05_StackPull20", stack & (l <= d.sma20) & (c > d.sma20))
    add("C05_StackPull50", stack & (l <= d.sma50) & (c > d.sma50))
    for m in (3, 5, 10):
        add(f"C06_Reclaim{m}_afterDD", (c > d[f"sma{m}"]) & (c.shift() < d[f"sma{m}"].shift()) & (d.dd < -0.03))
    add("C07_Double7_bull", bull_soft & d.ll7)
    add("C07_Double10_bull", bull_soft & d.ll10)
    add("C08_MomFailure", d.ll5 & (d.cumret5 > d.cumret5.shift(3)) & (d.rsi2 > d.rsi2.shift(3)) & bull_soft)

    # ============ D  VWAP family ======================================================
    for vw in ("wvwap", "mvwap"):
        sd = d[vw + "_sd"]
        for k in (1.0, 1.5, 2.0):
            below = c < d[vw] - k * sd
            add(f"D01_{vw}-{k}sd", bull_soft & below)
            add(f"D01_{vw}-{k}sd_reclaim", below.shift().fillna(False) & (c > d[vw] - k * sd))
    add("D03_MultiAnchor", (c < d.wvwap) & (c < d.mvwap) & (c > d.qvwap) & bull_soft)
    add("D03_MultiAnchor_up", (c < d.wvwap) & (c < d.mvwap) & (c > d.qvwap) & (c > c.shift()))
    for vw in ("wvwap", "mvwap"):
        add(f"D04_{vw}_undercut_reclaim", (c.shift() < d[vw].shift()) & (c > d[vw]))
    for k in (0.5, 1.0, 1.5):
        add(f"D05_AVWAPshock-{k}ATR", bull_soft & (d.dist_avwap_atr < -k))
    add("D05_AVWAPshock_reclaim", (d.dist_avwap_atr > 0) & (d.dist_avwap_atr.shift() < 0) & (d.dd < -0.02))
    add("D05_AVWAPpeak_reclaim", (d.dist_avwap_peak_atr > 0) & (d.dist_avwap_peak_atr.shift() < 0) & (d.dd < -0.03))

    # ============ E  value area (1-min volume profile proxy) ===========================
    add("E01_VALsweep_reclaim", (l < d.val.shift()) & (c > d.val.shift()))
    add("E01_VALsweep_bull", bull_soft & (l < d.val.shift()) & (c > d.val.shift()))
    add("E01_WeekVALsweep", (l < d.pw_val) & (c > d.pw_val))
    add("E02_BelowVAL_return", (c.shift() < d.val.shift(2)) & (c > d.val.shift()))
    add("E03_VALacceptFail", (c.shift() < d.pw_val) & (c.shift(2) < d.pw_val) & (c > d.pw_val))
    add("E04_POCup_priceDown", (d.poc > d.poc.shift()) & (c < c.shift()) & bull_soft)
    add("E04_POCup_lowerLow", (d.poc > d.poc.shift()) & (l < l.shift()) & (c > o))
    add("E05_ValueOverlap_reject", (abs(d.poc - d.poc.shift()) < 0.3 * atr) & (l < d.val.shift()) & (c > d.val.shift()))
    add("E07_NakedPOC_above", (c < d.pw_poc) & (c > d.pw_val) & bull_soft & (c > c.shift()))

    # ============ F  delta exhaustion =================================================
    for z in (-1.0, -1.5, -2.0, -3.0):
        add(f"F01_DeltaZ{z}_loc", (d.delta_z < z) & (d.dd < -0.02) & (d.ibs > 0.3))
        add(f"F01_DeltaZ{z}_flip", (d.delta_z.shift() < z) & (d.eth_delta > 0))
    for k in (3, 5, 10):
        add(f"F02_PriceDeltaDiv{k}", (c < c.shift(k)) & (d[f"cd{k}"] > 0))
        add(f"F02_PriceDeltaDiv{k}_trig", (c.shift() < c.shift(k + 1)) & (d[f"cd{k}"].shift() > 0) & (c > h.shift()))
    for pr in (0.15, 0.25, 0.4):
        add(f"F03_EffortNoResult{int(pr*100)}", (d.delta_z < -1.0) & (d.price_response < pr))
        add(f"F03_EffortNoResult{int(pr*100)}_loc", (d.delta_z < -1.0) & (d.price_response < pr) & (d.dd < -0.02))
    add("F05_ClimaxFlip", d.climax_flip)
    add("F05_ClimaxFlip_bull", bull_soft & d.climax_flip)
    add("F06_CVDlow_priceHolds", d.cvd_lower_price_holds & bull_soft)
    add("F06_CVDhigherLow", d.cvd_higher_low)
    add("F09_FailedNegContinuation", d.failed_neg_continuation)
    add("F09_FailedNeg_stop", d.failed_neg_continuation, emode=3, llim=h)

    # ============ G  combined engines =================================================
    weak = (d.downdays >= 3) | (d.cumret5_pct < 0.05)
    loc = bull_soft & ((c < d.wvwap) | (c < d.sma20))
    add("G01_Weak_Loc_Trig", weak & loc & (c > h.shift()))
    add("G01_Weak_Loc_VWAPreclaim", weak.shift().fillna(False) & loc.shift().fillna(False) & (c > d.wvwap) & (c.shift() < d.wvwap.shift()))
    add("G01_Weak_Loc_open", weak & loc)
    add("G02_DD_Delta_VAL", (d.dd < -0.03) & (d.price_response < 0.3) & (l < d.pw_val) & (c > d.pw_val))
    add("G02_DD_Delta", (d.dd < -0.03) & (d.delta_z < -1.0) & (d.ibs > 0.4))
    # two-stage: weakness armed within the last 5 sessions, then a confirmation trigger
    armed = ((d.dd < -0.03) | (d.cumret5_pct < 0.05)).rolling(5).max().astype(bool)
    add("G03_TwoStage_SMA3", armed & (c > d.sma3) & (c.shift() < d.sma3.shift()))
    add("G03_TwoStage_prevHigh", armed & (c > h.shift()))
    add("G03_TwoStage_delta", armed & d.delta_flip)
    add("G03_TwoStage_stop", armed, emode=3, llim=h)
    # G08 bear-market rally short (the only short family here)
    no = np.zeros(len(d), bool)
    add("G08_BearRallyShort", no, bear & (d.rsi2 > 90) & (c < d.sma50))
    add("G08_BearRally_VWAPfail", no, bear & (h >= d.wvwap) & (c < d.wvwap))
    add("G08_BearRally_failReclaim", no, bear & (c.shift() > d.sma20.shift()) & (c < d.sma20))
    return out
