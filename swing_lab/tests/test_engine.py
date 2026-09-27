"""Deterministic execution tests for engine.run on synthetic bars (python -m pytest tests)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import run  # noqa: E402

INF = np.inf


def market(days):
    """days: list of (on_bars, rth_bars) with bars = [(o, h, l, c), ...]; returns engine arrays"""
    bo, bh, bl, bc, start, end = [], [], [], [], [], []
    O, H, L, C, oO, oH, oL = ([] for _ in range(7))
    for on, rth in days:
        for seg in (on, rth):
            start.append(len(bo))
            for o, h, l, c in seg:
                bo.append(o); bh.append(h); bl.append(l); bc.append(c)
            end.append(len(bo))
        O.append(rth[0][0]); H.append(max(b[1] for b in rth)); L.append(min(b[2] for b in rth)); C.append(rth[-1][3])
        oO.append(on[0][0]); oH.append(max(b[1] for b in on)); oL.append(min(b[2] for b in on))
    f = lambda x: np.array(x, dtype=np.float64)  # noqa: E731
    return [f(O), f(H), f(L), f(C), f(oO), f(oH), f(oL), f(bo), f(bh), f(bl),
            np.array(start, np.int64), np.array(end, np.int64)]


def go(days, side, emode=0, lim=None, sl=INF, tp=INF, tr=INF, tr_act=0.0, be_r=0.0, max_days=0, xsig=None, cost=0.0):
    m = market(days)
    n = len(days)
    s = np.zeros(n, np.int8); s[0] = side
    lim_a = np.full(n, 0.0 if lim is None else lim)
    x = np.zeros(n, np.int8) if xsig is None else np.array(xsig, np.int8)
    out = run(s, emode, lim_a, np.full(n, float(sl)), np.full(n, float(tp)), np.full(n, float(tr)), tr_act, be_r,
              max_days, x, 0, cost, *m[:7], *m[7:], 0, n)
    return out


FLAT = [(100, 100, 100, 100)]


def test_close_entry_stop_overnight_gap():
    days = [(FLAT, [(100, 101, 99, 100)]),
            ([(95, 96, 94, 95)], [(95, 96, 94, 95)])]          # gap below stop overnight
    out = go(days, 1, sl=2.0)
    assert out[8][0] == -5.0                                      # filled at the gap open, not at the stop
    assert out[11][0] == 1


def test_limit_fill_bar_stop_is_counted():
    # day0 signal, day1 limit at 98: the fill bar trades down to 95 -> stop 96 hit in the fill bar
    days = [(FLAT, [(100, 100, 100, 100)]),
            (FLAT, [(99, 99, 95, 97), (97, 110, 97, 109)])]
    out = go(days, 1, emode=2, lim=98.0, sl=2.0, tp=5.0)
    assert out[11][0] == 1 and out[8][0] == -2.0                  # stop first, TP in later bar ignored


def test_tp_and_sl_same_segment_resolved_by_bars():
    days = [(FLAT, [(100, 100, 100, 100)]),
            (FLAT, [(100, 104, 99.5, 103), (103, 103, 97, 98)])]  # TP 104 first, stop 98 later
    out = go(days, 1, sl=2.0, tp=4.0)
    assert out[11][0] == 2 and out[8][0] == 4.0


def test_same_bar_tp_sl_is_stop_first():
    days = [(FLAT, [(100, 100, 100, 100)]),
            (FLAT, [(100, 105, 97, 101)])]
    out = go(days, 1, sl=2.0, tp=4.0)
    assert out[11][0] == 1 and out[8][0] == -2.0


def test_trailing_updates_inside_segment():
    # rally to 110 then reversal to 103 inside one RTH session: 3-pt trail must exit at 107
    days = [(FLAT, [(100, 100, 100, 100)]),
            (FLAT, [(100, 105, 100, 105), (105, 110, 105, 110), (110, 110, 103, 103)])]
    out = go(days, 1, sl=5.0, tr=3.0)
    assert out[11][0] == 3 and out[8][0] == 7.0


def test_short_mirror_and_time_stop():
    days = [(FLAT, [(100, 100, 100, 100)]), (FLAT, [(100, 100, 97, 98)]), (FLAT, [(98, 99, 96, 96)])]
    out = go(days, -1, max_days=2)
    assert out[11][0] == 4 and out[8][0] == 4.0


def test_cost_is_charged_once():
    days = [(FLAT, [(100, 100, 100, 100)]), (FLAT, [(100, 101, 100, 101)])]
    out = go(days, 1, max_days=1, cost=0.5)
    assert abs(out[8][0] - 0.5) < 1e-9 and abs(out[0].sum() - 0.5) < 1e-9
