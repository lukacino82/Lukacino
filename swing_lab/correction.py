"""
Correction-state features (CORRECTION_ALPHA_BLUEPRINT sections A, B, D, F).

Everything is causal: row t uses only bars <= t. The correction state machine is

    0 trend  ->  1 weakness  ->  2 impulse  ->  3 exhaustion  ->  4 armed  ->  5 recovery/failure

and is rebuilt forward bar by bar, so no feature ever knows where the trough will be.
Percentile thresholds are rolling ranks inside a trailing window, never full-sample quantiles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _peak_state(close: np.ndarray, high: np.ndarray, win: int):
    """running peak of the trailing `win` sessions and the low made since that peak.
    Returns (peak, days_since_peak, corr_low, days_since_corr_low) - all causal."""
    n = len(close)
    peak = np.full(n, np.nan)
    since_pk = np.zeros(n)
    clow = np.full(n, np.nan)
    since_lo = np.zeros(n)
    pk = -np.inf
    pk_i = 0
    lo = np.inf
    lo_i = 0
    for i in range(n):
        if high[i] >= pk:                       # new peak -> correction state resets
            pk, pk_i = high[i], i
            lo, lo_i = close[i], i
        elif close[i] <= lo:
            lo, lo_i = close[i], i
        # a peak older than `win` sessions is no longer the reference: re-scan the window
        if i - pk_i > win:
            j0 = max(0, i - win + 1)
            pk_i = j0 + int(np.argmax(high[j0:i + 1]))
            pk = high[pk_i]
            lo_i = pk_i + int(np.argmin(close[pk_i:i + 1]))
            lo = close[lo_i]
        peak[i], since_pk[i], clow[i], since_lo[i] = pk, i - pk_i, lo, i - lo_i
    return peak, since_pk, clow, since_lo


def _anchored_vwap(tp: np.ndarray, vol: np.ndarray, anchor: np.ndarray):
    """VWAP restarted whenever anchor[i] is True (anchor day included)."""
    n = len(tp)
    out = np.full(n, np.nan)
    cv = ctpv = 0.0
    for i in range(n):
        if anchor[i] or cv == 0:
            cv = ctpv = 0.0
        ctpv += tp[i] * vol[i]
        cv += vol[i]
        out[i] = ctpv / cv if cv > 0 else np.nan
    return out


def add_correction_features(d: pd.DataFrame) -> pd.DataFrame:
    c, h, l, o = d.close, d.high, d.low, d.open
    pc = c.shift()
    atr = d.atr20
    r = c.pct_change()
    n = len(d)

    # ---- A: weakness, streaks, shocks -------------------------------------------------
    d["cumret2"], d["cumret3"], d["cumret5"], d["cumret10"] = (c / c.shift(k) - 1 for k in (2, 3, 5, 10))
    for k in (2, 3, 5, 10):                       # rolling percentile of the k-day return (causal)
        d[f"cumret{k}_pct"] = d[f"cumret{k}"].rolling(504, min_periods=120).rank(pct=True)
    d["atr_shock"] = -(c - pc) / atr.shift()      # 1-day drop in ATRs (positive = down)
    d["atr_shock2"] = -(c - c.shift(2)) / atr.shift(2)
    d["gap_atr"] = d.gap / atr.shift()
    d["rth_move_atr"] = (c - o) / atr.shift()
    # weighted losing streak: signed sum of ATR-normalised returns over the last k sessions
    rn = (c - pc) / atr.shift()
    for k in (3, 5, 7):
        d[f"wstreak{k}"] = rn.rolling(k).sum()
    d["down_effort"] = ((o - c) / (h - l).replace(0, np.nan)).clip(-1, 1)   # body share of a down bar
    # accelerating: three down days, each bigger than the last; decelerating: smaller drop than before
    dn = rn < 0
    d["accel_down"] = dn & dn.shift(1) & dn.shift(2) & (rn < rn.shift(1)) & (rn.shift(1) < rn.shift(2))
    d["decel_down"] = dn & dn.shift(1) & (rn > rn.shift(1)) & (c < c.shift(2))
    d["range_shrink"] = (h - l) < (h - l).shift()
    d["vol_shrink"] = d.volume < d.volume.shift()
    # failed breakdown / sweeps of the last N-session low
    for N in (5, 10, 20):
        prev_low = l.rolling(N).min().shift()
        d[f"sweep{N}"] = (l < prev_low) & (c > prev_low)
        d[f"below{N}"] = c < prev_low
    d["outside_rev"] = (l < l.shift()) & (h > h.shift()) & (d.ibs > 0.6)
    d["inside_day"] = (h < h.shift()) & (l > l.shift())
    d["gap_down_recover"] = (d.gap_atr < -0.5) & (c > o)
    d["higher_low"] = (l > l.shift()) & (l.shift() < l.shift(2))

    # ---- B: drawdown anatomy ----------------------------------------------------------
    for win, tag in ((252, ""), (63, "q")):
        peak, spk, clow, slo = _peak_state(c.values, h.values, win)
        d[f"peak{tag}"] = peak
        d[f"dd{tag}"] = c.values / peak - 1
        d[f"days_from_peak{tag}"] = spk
        d[f"corr_low{tag}"] = clow
        d[f"days_from_low{tag}"] = slo
        rng = np.maximum(peak - clow, 1e-9)
        d[f"recovery_frac{tag}"] = (c.values - clow) / rng
        d[f"dd_velocity{tag}"] = d[f"dd{tag}"] / np.maximum(spk, 1)          # depth per session
        d[f"dd_atr{tag}"] = (c.values - peak) / atr.values
    d["dd_bucket"] = pd.cut(d.dd, [-1, -0.20, -0.15, -0.10, -0.075, -0.05, -0.03, -0.02, 0.001],
                            labels=["20+", "15-20", "10-15", "7.5-10", "5-7.5", "3-5", "2-3", "0-2"])
    d["time_under_water"] = d.days_from_peak * (-d.dd)                        # depth x duration
    d["new_corr_low"] = (d.days_from_low == 0) & (d.dd < -0.01)
    d["retest_low"] = (d.days_from_low >= 2) & ((c - d.corr_low) / atr < 0.5) & (d.dd < -0.02)

    # ---- D: anchored VWAP -------------------------------------------------------------
    tp = ((h + l + c) / 3).values
    vol = d.volume.values.astype(float)
    shock = (d.atr_shock > 1.0).fillna(False).values          # mechanical anchor: first 1-ATR down day
    anchor = shock & ~pd.Series(shock).shift(1, fill_value=False).values
    d["avwap_shock"] = _anchored_vwap(tp, vol, anchor)
    d["dist_avwap_atr"] = (c - d.avwap_shock) / atr
    pk_new = (d.days_from_peak == 0).values
    d["avwap_peak"] = _anchored_vwap(tp, vol, pk_new)
    d["dist_avwap_peak_atr"] = (c - d.avwap_peak) / atr

    # ---- F: delta effort versus result ------------------------------------------------
    # how many ATRs of price does one unit of aggressive selling buy? small = absorption
    sell = (-d.delta_z).clip(lower=0.1)
    d["price_response"] = (-rn).clip(lower=0) / sell
    d["effort_no_result"] = (d.delta_z < -1.0) & (d.price_response < 0.25)
    d["delta_flip"] = (d.eth_delta > 0) & (d.eth_delta.shift() < 0)
    d["cvd_higher_low"] = d.ll10 & (d.cumdelta > d.cumdelta.rolling(10).min().shift())
    d["cvd_lower_price_holds"] = (d.cumdelta < d.cumdelta.rolling(10).min().shift()) & ~d.ll10
    d["delta_climax"] = (d.delta_z < -1.5) & (d.tr > 1.2 * atr)
    d["climax_flip"] = d.delta_climax.shift().fillna(False) & (l > l.shift() - 0.1 * atr) & (d.eth_delta > d.eth_delta.shift())
    d["failed_neg_continuation"] = (d.delta_z < -0.5) & (d.delta_z.shift() < -1.0) & (l > l.shift())
    return d.copy()
