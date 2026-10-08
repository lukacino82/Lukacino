"""Same idea as sweep_exits.py, but on FIXED point distances instead of
multiples of each trade's own structural_risk.

sweep_exits.py's "stop_multiplier x structural_risk" answers "does scaling
the stop relative to this trade's own structural level help" -- it does NOT
tell you how many points that actually is, and the real-ES median
structural_risk turned out to be tiny (~2.9pts), so its "best" combo
(0.5x stop, 3:1 RRR) corresponds to a ~1.4pt median stop -- not a
realistically tradeable distance on ES (sub-spread). This script answers
the practically useful question instead: for a FIXED SL in points (same for
every trade, matching how a discretionary trader like the user's G7FX
reference actually places orders -- "always risk ~10pts"), which TP
distance (also fixed points, or expressed as that SL's RRR) works best.

Usage:
    python3 sweep_exits_fixed_points.py <capture_dir> <out_csv> [max_lookahead_bars]
"""
from __future__ import annotations

import array
import csv
import sys
from pathlib import Path

SL_POINTS = [3, 5, 8, 10, 12, 15, 20, 25, 30]
RRRS = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]


def load_entries(path: Path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def simulate(entries, prices: array.array, sl_points: float, rrr: float, max_lookahead: int):
    wins = losses = opens = 0
    total_r = 0.0
    for e in entries:
        idx = int(e["entry_index"])
        entry_price = float(e["entry_price"])
        direction = e["direction"]
        target_points = rrr * sl_points
        stop_price = entry_price - sl_points if direction == "long" else entry_price + sl_points
        target_price = entry_price + target_points if direction == "long" else entry_price - target_points

        end = min(idx + 1 + max_lookahead, len(prices))
        outcome = None
        for j in range(idx + 1, end):
            p = prices[j]
            stop_hit = p <= stop_price if direction == "long" else p >= stop_price
            target_hit = p >= target_price if direction == "long" else p <= target_price
            if stop_hit or target_hit:
                outcome = "loss" if stop_hit else "win"
                break
        if outcome == "win":
            wins += 1
            total_r += rrr
        elif outcome == "loss":
            losses += 1
            total_r -= 1.0
        else:
            opens += 1
    resolved = wins + losses
    win_rate = wins / resolved if resolved else None
    return {
        "sl_points": sl_points, "tp_points": sl_points * rrr, "rrr": rrr,
        "trades": len(entries), "wins": wins, "losses": losses, "open": opens,
        "win_rate": win_rate, "total_r": total_r,
        "expectancy_r": total_r / resolved if resolved else None,
        "expectancy_points_per_trade": (total_r / resolved) * sl_points if resolved else None,
    }


def main() -> None:
    capture_dir = Path(sys.argv[1])
    out_csv = sys.argv[2]
    max_lookahead = int(sys.argv[3]) if len(sys.argv) > 3 else 3000

    entries = load_entries(capture_dir / "entries.csv")
    prices = array.array("d")
    with open(capture_dir / "prices.bin", "rb") as f:
        prices.frombytes(f.read())
    print(f"{len(entries):,} entries, {len(prices):,} prices", file=sys.stderr)

    results = []
    for sl in SL_POINTS:
        for rrr in RRRS:
            r = simulate(entries, prices, sl, rrr, max_lookahead)
            results.append(r)
            print(
                f"  SL={sl}pt TP={sl*rrr:.1f}pt (rrr={rrr}): {r['trades']} trades, "
                f"win_rate={r['win_rate']}, total_r={r['total_r']:+.1f}",
                file=sys.stderr,
            )

    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"Done: {len(results)} combinations written to {out_csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
