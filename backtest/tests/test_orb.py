"""Testy logiky ORB na ručně sestavených dnech (5min svíčky, 9:30 NY).

Spuštění:  python -m unittest discover -s backtest/tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orb_backtest import build_parser, load_bars, run_day, stats  # noqa: E402


def params(*argv):
    return build_parser().parse_args(["dummy.txt", *argv])


def t(hh, mm):
    return hh * 3600 + mm * 60


# Opening range 9:30–9:45 (3 svíčky): high 102, low 98
RANGE = [
    (t(9, 30), 100, 101, 99, 100),
    (t(9, 35), 100, 102, 98, 101),
    (t(9, 40), 101, 101.5, 99, 100),
]


class OrbLogic(unittest.TestCase):
    def test_long_hits_target(self):
        # close 103 > 102 -> long, SL 98, risk 5, RRR 1.5 -> TP 110.5
        day = RANGE + [
            (t(9, 45), 100, 103.5, 100, 103),
            (t(9, 50), 103, 108, 102, 107),
            (t(9, 55), 107, 111, 106, 110),
        ]
        pts, side, entry, exit_, reason = run_day(day, params("--rrr", "1.5"))
        self.assertEqual((side, entry, exit_, reason), (1, 103, 110.5, "TP"))
        self.assertAlmostEqual(pts, 7.5)

    def test_short_hits_stop(self):
        # close 97 < 98 -> short, SL 102, risk 5
        day = RANGE + [
            (t(9, 45), 99, 99, 96.5, 97),
            (t(9, 50), 97, 102.25, 96, 102),
        ]
        pts, side, entry, exit_, reason = run_day(day, params("--rrr", "2"))
        self.assertEqual((side, reason), (-1, "SL"))
        self.assertAlmostEqual(pts, -5)

    def test_same_bar_sl_and_tp_counts_as_loss(self):
        day = RANGE + [
            (t(9, 45), 100, 103, 100, 103),       # long @103, SL 98, TP 108 (RRR 1)
            (t(9, 50), 103, 109, 97, 105),        # zasáhne oboje
        ]
        pts, *_ , reason = run_day(day, params("--rrr", "1"))
        self.assertEqual(reason, "SL")
        self.assertAlmostEqual(pts, -5)

    def test_eod_exit(self):
        day = RANGE + [(t(9, 45), 100, 103, 100, 103)]
        day += [(t(10, 0) + k * 300, 103, 104, 102, 103.5) for k in range(72)]  # do 15:55
        pts, side, entry, exit_, reason = run_day(day, params("--rrr", "3"))
        self.assertEqual(reason, "EOD")
        self.assertAlmostEqual(pts, 0.5)

    def test_no_breakout_no_trade(self):
        day = RANGE + [(t(9, 45) + k * 300, 100, 101.5, 98.5, 100) for k in range(20)]
        self.assertIsNone(run_day(day, params()))

    def test_breakout_after_last_entry_ignored(self):
        day = RANGE + [(t(9, 45) + k * 300, 100, 101, 99, 100) for k in range(21)]  # do 11:25
        day += [(t(11, 35), 100, 104, 100, 103.5)]
        self.assertIsNone(run_day(day, params()))

    def test_direction_long_only_skips_short(self):
        day = RANGE + [(t(9, 45), 99, 99, 96, 97)]
        self.assertIsNone(run_day(day, params("--direction", "long")))

    def test_mid_stop(self):
        # mid = 100, long @103 -> risk 3, RRR 2 -> TP 109
        day = RANGE + [
            (t(9, 45), 100, 103, 100, 103),
            (t(9, 50), 103, 109.25, 102, 109),
        ]
        pts, *_, reason = run_day(day, params("--stop", "mid", "--rrr", "2"))
        self.assertEqual(reason, "TP")
        self.assertAlmostEqual(pts, 6)

    def test_fixed_ticks_stop_and_target(self):
        # long @103, SL 20 ticků = 5 b -> 98, TP 12 ticků = 3 b -> 106
        day = RANGE + [
            (t(9, 45), 100, 103, 100, 103),
            (t(9, 50), 103, 106.25, 102, 106),
        ]
        pts, *_, reason = run_day(day, params("--stop", "fixed", "--stop-ticks", "20", "--target-ticks", "12"))
        self.assertEqual(reason, "TP")
        self.assertAlmostEqual(pts, 3)

    def test_fixed_stop_with_rrr(self):
        # short @97, SL 8 ticků = 2 b -> 99, RRR 2 -> TP 93
        day = RANGE + [
            (t(9, 45), 99, 99, 96.5, 97),
            (t(9, 50), 97, 98, 92.75, 93),
        ]
        pts, *_, reason = run_day(day, params("--stop", "fixed", "--stop-ticks", "8", "--rrr", "2"))
        self.assertEqual(reason, "TP")
        self.assertAlmostEqual(pts, 4)

    def test_max_range_filter(self):
        # range 4 body = 16 ticků
        day = RANGE + [(t(9, 45), 100, 103, 100, 103)]
        self.assertIsNone(run_day(day, params("--max-ticks", "10")))

    def test_only_one_trade_per_day(self):
        day = RANGE + [
            (t(9, 45), 100, 103, 100, 103),   # long
            (t(9, 50), 103, 103, 97.5, 98),   # SL
            (t(9, 55), 98, 98, 90, 91),       # nový breakdown -> nic
        ]
        _, side, *_, reason = run_day(day, params())
        self.assertEqual((side, reason), (1, "SL"))

    def test_stats_money(self):
        p = params("--point-value", "50", "--commission", "4")
        s = stats([5, -5, 10], p)
        self.assertEqual(s["trades"], 3)
        self.assertAlmostEqual(s["net"], 10 * 50 - 3 * 4)
        self.assertAlmostEqual(s["maxdd"], -254)


class Resample(unittest.TestCase):
    def test_1min_to_5min(self):
        import tempfile
        rows = ["Date, Time, Open, High, Low, Last, Volume"]
        for m in range(10):  # 9:30..9:39
            rows.append(f"2025/1/2, 09:{30+m}:00, {100+m}, {101+m}, {99+m}, {100.5+m}, 1")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("\n".join(rows))
        bars = load_bars(f.name, resample=5)["2025/1/2"]
        os.unlink(f.name)
        self.assertEqual(bars, [(t(9, 30), 100, 105, 99, 104.5), (t(9, 35), 105, 110, 104, 109.5)])


if __name__ == "__main__":
    unittest.main()
