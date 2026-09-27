"""
Numba swing backtest engine (1 contract, P&L in ES points, 1 pt = $50).

Each trading day d has two segments: ON (overnight, before 09:30) and RTH (09:30-16:00).
Protective orders (SL, TP, trailing, breakeven) are live in both segments. When SL and TP are
both inside one segment's range the path is resolved on 30-minute bars; inside a single
30-minute bar the stop is assumed to fill first (conservative). Gaps through a level fill at the
segment/bar open.

Entry modes (signal known at RTH close of day d):
  0 CLOSE      fill at close of d (MOC / last minutes), exposed from the next ON segment
  1 NEXT_OPEN  fill at RTH open of d+1
  2 LIMIT      resting limit at lim[d] during day d+1 (ON + RTH); long fill = min(lim, bar open)
  3 STOP       resting stop at lim[d] during day d+1;           long fill = max(lim, bar open)
Exit rules (optional, first touched wins):
  sl_d[d]   stop-loss distance in points (np.inf = none)
  tp_d[d]   take-profit distance in points (np.inf = none)
  tr_d[d]   chandelier trailing distance from best price since entry (np.inf = none), updated
            bar by bar on 30-min bars (never inside a bar: stop uses the previous bars' best),
            active once MFE >= tr_act * initial SL distance (tr_act = 0 -> from entry)
  be_r      move stop to entry(+cost) once MFE >= be_r * SL distance (0 = off)
  max_days  time stop: exit at RTH close after N sessions in the trade (0 = off)
  xsig[d]   exit signal at close of d: value == side or 2 exits; xmode 0 = at close, 1 = next open
"""
from __future__ import annotations

import numpy as np
from numba import njit

REASONS = {1: "sl", 2: "tp", 3: "trail", 4: "time", 5: "signal", 6: "breakeven", 7: "end_of_data"}


@njit(cache=True)
def _walk(side, stop, tp, k0, k1, bo, bh, bl):
    """walk 30-min bars k0..k1-1 -> (price, code, best, worst) code 1=stop 2=tp 0=none"""
    best = -1e18 if side > 0 else 1e18
    worst = 1e18 if side > 0 else -1e18
    for k in range(k0, k1):
        if side > 0:
            if bo[k] <= stop:
                return bo[k], 1, best, min(worst, bo[k])
            if bo[k] >= tp:
                return bo[k], 2, max(best, bo[k]), worst
            if bl[k] <= stop:
                return stop, 1, max(best, bh[k]), stop
            if bh[k] >= tp:
                return tp, 2, tp, min(worst, bl[k])
            best = max(best, bh[k])
            worst = min(worst, bl[k])
        else:
            if bo[k] >= stop:
                return bo[k], 1, best, max(worst, bo[k])
            if bo[k] <= tp:
                return bo[k], 2, min(best, bo[k]), worst
            if bh[k] >= stop:
                return stop, 1, min(best, bl[k]), stop
            if bl[k] <= tp:
                return tp, 2, tp, max(worst, bh[k])
            best = min(best, bl[k])
            worst = max(worst, bh[k])
    return 0.0, 0, best, worst


@njit(cache=True)
def _eff_stop(side, ep, stop, best, trail, trail_on, be_r, sl0, cost):
    """effective protective stop from initial stop, chandelier trail and breakeven -> (price, reason)"""
    eff = stop
    rs = 1
    if trail_on and trail < 1e17:
        ts = best - side * trail
        if side * (ts - eff) > 0:
            eff = ts
            rs = 3
    if be_r > 0.0 and side * (best - ep) >= be_r * sl0:
        bp = ep + side * cost
        if side * (bp - eff) > 0:
            eff = bp
            rs = 6
    return eff, rs


@njit(cache=True)
def _walk_dyn(side, ep, stop, tp, trail, trail_on, tr_act, be_r, sl0, cost, best, worst,
              k0, k1, first_is_fill, bo, bh, bl):
    """Replay 30-min bars k0..k1-1 with stops updated bar by bar (conservative).
    Bar k0 is the fill bar when first_is_fill: its open precedes the fill, so only a stop touch
    is checked there (a take-profit in the fill bar is ignored - order unknown).
    Inside one bar the stop uses the best price of *previous* bars and is assumed to hit first.
    -> (exit_price, code, best, worst, trail_on)"""
    for k in range(k0, k1):
        eff, rs = _eff_stop(side, ep, stop, best, trail, trail_on, be_r, sl0, cost)
        fill_bar = first_is_fill and k == k0
        if side > 0:
            if not fill_bar:
                if bo[k] <= eff:
                    return bo[k], rs, best, min(worst, bo[k]), trail_on
                if bo[k] >= tp:
                    return bo[k], 2, max(best, bo[k]), worst, trail_on
            if bl[k] <= eff:
                return min(eff, ep) if fill_bar and eff > ep else eff, rs, best, min(worst, eff), trail_on
            if (not fill_bar) and bh[k] >= tp:
                return tp, 2, tp, min(worst, bl[k]), trail_on
            best = max(best, bh[k])
            worst = min(worst, bl[k])
        else:
            if not fill_bar:
                if bo[k] >= eff:
                    return bo[k], rs, best, max(worst, bo[k]), trail_on
                if bo[k] <= tp:
                    return bo[k], 2, min(best, bo[k]), worst, trail_on
            if bh[k] >= eff:
                return max(eff, ep) if fill_bar and eff < ep else eff, rs, best, max(worst, eff), trail_on
            if (not fill_bar) and bl[k] <= tp:
                return tp, 2, tp, max(worst, bh[k]), trail_on
            best = min(best, bl[k])
            worst = max(worst, bh[k])
        if (not trail_on) and tr_act > 0.0 and side * (best - ep) >= tr_act * sl0:
            trail_on = True
    return 0.0, 0, best, worst, trail_on


@njit(cache=True)
def run(side_sig, emode, lim, sl_d, tp_d, tr_d, tr_act, be_r, max_days, xsig, xmode, cost,
        O, H, L, C, oO, oH, oL, bo, bh, bl, bstart, bend, start_i, end_i):
    n = len(C)
    pnl = np.zeros(n)
    pos = np.zeros(n, dtype=np.int8)
    t_sig = np.empty(n, dtype=np.int64)
    t_ent = np.empty(n, dtype=np.int64)
    t_exit = np.empty(n, dtype=np.int64)
    t_side = np.empty(n, dtype=np.int8)
    t_ep = np.empty(n)
    t_xp = np.empty(n)
    t_pnl = np.empty(n)
    t_mae = np.empty(n)
    t_mfe = np.empty(n)
    t_reason = np.empty(n, dtype=np.int8)
    nt = 0

    side = 0
    ep = 0.0
    stop = 0.0
    tp = 0.0
    trail = np.inf
    sl0 = 0.0
    best = 0.0
    worst = 0.0
    mark = 0.0
    held = 0
    sig_day = 0
    ent_day = 0
    trail_on = False
    exit_next_open = False
    pending = 0
    p_lim = 0.0
    p_day = 0

    for d in range(start_i, end_i):
        first_seg = 0
        fill_k = -1
        # ------------------------------------------------ pending order for today
        if pending != 0:
            sgn = pending
            pending = 0
            filled = False
            fill = 0.0
            if emode == 1:
                filled = True
                fill = O[d]
                first_seg = 1
            else:
                for seg in range(2):
                    k0 = bstart[d * 2 + seg]
                    k1 = bend[d * 2 + seg]
                    for k in range(k0, k1):
                        if emode == 2:
                            hit = (bl[k] <= p_lim) if sgn > 0 else (bh[k] >= p_lim)
                        else:
                            hit = (bh[k] >= p_lim) if sgn > 0 else (bl[k] <= p_lim)
                        if hit:
                            if emode == 2:
                                fill = min(p_lim, bo[k]) if sgn > 0 else max(p_lim, bo[k])
                            else:
                                fill = max(p_lim, bo[k]) if sgn > 0 else min(p_lim, bo[k])
                            filled = True
                            first_seg = seg
                            fill_k = k       # fill bar is replayed: stop checked first (conservative)
                            break
                    if filled:
                        break
            if filled:
                side = sgn
                ep = fill
                sl0 = sl_d[p_day]
                stop = ep - side * sl0
                tp = ep + side * tp_d[p_day]
                trail = tr_d[p_day]
                trail_on = tr_act <= 0.0
                best = ep
                worst = ep
                mark = ep
                held = 0
                sig_day = p_day
                ent_day = d
                exit_next_open = False

        # ------------------------------------------------ manage open position through today's segments
        if side != 0:
            code = 0
            px = 0.0
            for seg in range(first_seg, 2):
                if exit_next_open and seg == 1:
                    px = O[d]
                    code = 5
                    break
                eff, rs = _eff_stop(side, ep, stop, best, trail, trail_on, be_r, sl0, cost)
                k0 = bstart[d * 2 + seg]
                k1 = bend[d * 2 + seg]
                fill_seg = seg == first_seg and fill_k >= 0
                if fill_seg:
                    k0 = fill_k
                if seg == 0:
                    so, sh, sl_ = oO[d], oH[d], oL[d]
                else:
                    so, sh, sl_ = O[d], H[d], L[d]
                dynamic = trail < 1e17 or be_r > 0.0
                hs = (sl_ <= eff) if side > 0 else (sh >= eff)
                ht = (sh >= tp) if side > 0 else (sl_ <= tp)
                if fill_seg or dynamic or (hs and ht):
                    # bar-by-bar: fill bar replayed (stop first), trailing/breakeven updated per bar
                    px, code, best, worst, trail_on = _walk_dyn(
                        side, ep, stop, tp, trail, trail_on, tr_act, be_r, sl0, cost, best, worst,
                        k0, k1, fill_seg, bo, bh, bl)
                    if code != 0:
                        break
                else:
                    if hs:
                        px = min(so, eff) if side > 0 else max(so, eff)
                        code = rs
                        if side * (worst - px) > 0:
                            worst = px
                        break
                    if ht:
                        px = max(so, tp) if side > 0 else min(so, tp)
                        code = 2
                        if side * (px - best) > 0:
                            best = px
                        break
                    hi_fav = sh if side > 0 else sl_
                    hi_adv = sl_ if side > 0 else sh
                    if side * (hi_fav - best) > 0:
                        best = hi_fav
                    if side * (worst - hi_adv) > 0:
                        worst = hi_adv
                    if (not trail_on) and tr_act > 0.0 and side * (best - ep) >= tr_act * sl0:
                        trail_on = True
            if code == 0:
                held += 1
                pnl[d] += side * (C[d] - mark)
                mark = C[d]
                pos[d] = side
                if max_days > 0 and held >= max_days:
                    code = 4
                    px = C[d]
                elif xsig[d] == side or xsig[d] == 2:
                    if xmode == 0:
                        code = 5
                        px = C[d]
                    else:
                        exit_next_open = True
                if code != 0:
                    pnl[d] -= cost
            else:
                pnl[d] += side * (px - mark) - cost
                if seg == 1 or first_seg == 1:
                    pos[d] = side
            if code != 0:
                t_sig[nt] = sig_day
                t_ent[nt] = ent_day
                t_exit[nt] = d
                t_side[nt] = side
                t_ep[nt] = ep
                t_xp[nt] = px
                t_pnl[nt] = side * (px - ep) - cost
                t_mae[nt] = side * (worst - ep)
                t_mfe[nt] = side * (best - ep)
                t_reason[nt] = code
                nt += 1
                side = 0
                exit_next_open = False

        # ------------------------------------------------ new signal at the close of d
        if side == 0 and side_sig[d] != 0 and d + 1 < end_i:
            s = side_sig[d]
            if emode == 0:
                side = s
                ep = C[d]
                sl0 = sl_d[d]
                stop = ep - side * sl0
                tp = ep + side * tp_d[d]
                trail = tr_d[d]
                trail_on = tr_act <= 0.0
                best = ep
                worst = ep
                mark = ep
                held = 0
                sig_day = d
                ent_day = d
                exit_next_open = False
            else:
                pending = s
                p_lim = lim[d]
                p_day = d

    if side != 0:
        last = end_i - 1
        t_sig[nt] = sig_day
        t_ent[nt] = ent_day
        t_exit[nt] = last
        t_side[nt] = side
        t_ep[nt] = ep
        t_xp[nt] = C[last]
        t_pnl[nt] = side * (C[last] - ep) - cost
        t_mae[nt] = side * (worst - ep)
        t_mfe[nt] = side * (best - ep)
        t_reason[nt] = 7
        nt += 1
        pnl[last] -= cost
    return (pnl, pos, t_sig[:nt], t_ent[:nt], t_exit[:nt], t_side[:nt], t_ep[:nt], t_xp[:nt],
            t_pnl[:nt], t_mae[:nt], t_mfe[:nt], t_reason[:nt])
