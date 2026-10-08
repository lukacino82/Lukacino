"""Re-simulates every captured entry (capture_entries.py's entries.csv +
prices.bin) against a grid of stop/target combinations, without touching
the engine again -- each trade's entry is fixed (see capture_entries.py's
docstring on why entries themselves aren't re-decided per parameter set),
only how far its stop and target_1 would have sat is varied.

stop_distance = stop_multiplier * structural_risk (the entry's own
|entry - invalidation|, i.e. "how far was the original structural stop" --
sweeping a multiplier of it rather than an absolute point distance keeps
the grid meaningful across very different volatility regimes in 18 years
of data). target_distance = rrr * stop_distance.

Usage:
    python3 sweep_exits.py <capture_dir> <out_csv> [max_lookahead_bars]
"""
from __future__ import annotations

import array
import csv
import sys
from pathlib import Path

STOP_MULTIPLIERS = [0.5, 0.75, 1.0, 1.5, 2.0]
RRRS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]


def load_entries(path: Path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def simulate(entries, prices: array.array, stop_mult: float, rrr: float, max_lookahead: int):
    wins = losses = opens = 0
    total_r = 0.0
    for e in entries:
        idx = int(e["entry_index"])
        risk = float(e["structural_risk"])
        if risk <= 0:
            continue
        entry_price = float(e["entry_price"])
        direction = e["direction"]
        stop_dist = stop_mult * risk
        target_dist = rrr * stop_dist
        stop_price = entry_price - stop_dist if direction == "long" else entry_price + stop_dist
        target_price = entry_price + target_dist if direction == "long" else entry_price - target_dist

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
        "stop_multiplier": stop_mult, "rrr": rrr,
        "trades": len(entries), "wins": wins, "losses": losses, "open": opens,
        "win_rate": win_rate, "total_r": total_r,
        "expectancy_r": total_r / resolved if resolved else None,
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
    for stop_mult in STOP_MULTIPLIERS:
        for rrr in RRRS:
            r = simulate(entries, prices, stop_mult, rrr, max_lookahead)
            results.append(r)
            print(
                f"  stop_mult={stop_mult} rrr={rrr}: {r['trades']} trades, "
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
