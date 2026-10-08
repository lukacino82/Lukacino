"""Equity curves + pattern-mining breakdown over capture_entries.py's
entries.csv (the "as actually traded", target_1-based outcomes) and,
optionally, sweep_exits.py's sweep_results.csv (the TP/SL/RRR grid).

Produces PNGs (equity curves per long/short/A/B/counter/confluence split)
and a text report ranking every breakdown bucket by expectancy, so the
"which recurring setups actually have an edge" question has a concrete
answer instead of a single blended win rate.

Usage:
    python3 analyze_entries.py <capture_dir> <out_dir> [sweep_results.csv]
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Palette: deliberately colorblind-safe and consistent across every chart
# here -- blue for long/bullish, red/orange for short/bearish, grey for
# "all"/baseline, matching the convention every chart in this file reuses.
COLOR_ALL = "#4b5563"
COLOR_LONG = "#2563eb"
COLOR_SHORT = "#dc2626"
COLOR_A = "#059669"
COLOR_B = "#7c3aed"
COLOR_COUNTER = "#d97706"
COLOR_APLUS = "#059669"
COLOR_CLEAN = "#6b7280"


def load_entries(path: Path):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["actual_outcome"] == "open":
                continue  # excluded from every stat below -- not yet resolved
            row["actual_r_multiple"] = float(row["actual_r_multiple"])
            row["day_of_week"] = int(row["day_of_week"])
            row["hour"] = int(row["hour"])
            row["structural_risk"] = float(row["structural_risk"])
            row["has_composite"] = row["has_composite"] == "1"
            row["position_in_composite"] = float(row["position_in_composite"])
            rows.append(row)
    rows.sort(key=lambda r: r["timestamp"])
    return rows


def equity_curve(rows):
    cum = 0.0
    out = []
    for r in rows:
        cum += r["actual_r_multiple"]
        out.append(cum)
    return out


def plot_equity_group(rows, groups: dict, title: str, out_path: str):
    """``groups``: label -> predicate(row)->bool. Draws one line per group
    plus "All" so every split is visible against the unfiltered baseline.
    """
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    ax.plot(equity_curve(rows), label=f"All ({len(rows)})", color=COLOR_ALL, linewidth=1.5)
    palette = [COLOR_LONG, COLOR_SHORT, COLOR_A, COLOR_B, COLOR_COUNTER, COLOR_APLUS]
    for i, (label, pred) in enumerate(groups.items()):
        subset = [r for r in rows if pred(r)]
        if not subset:
            continue
        ax.plot(equity_curve(subset), label=f"{label} ({len(subset)})", color=palette[i % len(palette)], linewidth=1.3)
    ax.set_title(title)
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative R")
    ax.axhline(0, color="#d1d5db", linewidth=0.8, zorder=0)
    ax.legend(loc="upper left", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def bucket_stats(rows, key_fn):
    buckets: dict = defaultdict(list)
    for r in rows:
        buckets[key_fn(r)].append(r["actual_r_multiple"])
    out = []
    for key, rs in buckets.items():
        wins = sum(1 for x in rs if x > 0)
        out.append({
            "bucket": key, "trades": len(rs), "win_rate": wins / len(rs),
            "total_r": sum(rs), "expectancy_r": sum(rs) / len(rs),
        })
    out.sort(key=lambda b: -b["expectancy_r"])
    return out


def print_table(title, stats, f):
    f.write(f"\n=== {title} ===\n")
    f.write(f"{'bucket':30s} {'trades':>8s} {'win_rate':>9s} {'total_R':>10s} {'expectancy_R':>13s}\n")
    for s in stats:
        f.write(f"{str(s['bucket']):30s} {s['trades']:8d} {s['win_rate']:9.1%} {s['total_r']:+10.1f} {s['expectancy_r']:+13.3f}\n")


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def main() -> None:
    capture_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    rows = load_entries(capture_dir / "entries.csv")
    print(f"{len(rows):,} resolved trades loaded", file=sys.stderr)

    # --- Equity curves ---
    plot_equity_group(
        rows, {"Long": lambda r: r["direction"] == "long", "Short": lambda r: r["direction"] == "short"},
        "Equity curve -- Long vs Short", out_dir / "equity_long_short.png",
    )
    plot_equity_group(
        rows,
        {
            "A (A long/short)": lambda r: r["hypothesis_type"].startswith("A "),
            "B (B long/short)": lambda r: r["hypothesis_type"].startswith("B "),
            "Counter": lambda r: r["hypothesis_type"].startswith("Counter"),
        },
        "Equity curve -- A vs B vs Counter setups", out_dir / "equity_a_b_counter.png",
    )
    plot_equity_group(
        rows,
        {"A_PLUS (full risk)": lambda r: r["confluence"] == "a_plus", "CLEAN (half size)": lambda r: r["confluence"] == "clean"},
        "Equity curve -- A_PLUS vs CLEAN confluence", out_dir / "equity_confluence.png",
    )
    plot_equity_group(
        rows,
        {f"{t} ({'long' if 'long' in t.lower() or 'Long' in t else 'short'})": lambda r, t=t: r["hypothesis_type"] == t
         for t in sorted(set(r["hypothesis_type"] for r in rows))},
        "Equity curve -- every hypothesis type", out_dir / "equity_by_type.png",
    )

    # --- Pattern-mining breakdowns ---
    report_path = out_dir / "pattern_report.txt"
    with open(report_path, "w") as f:
        f.write(f"Total resolved trades: {len(rows):,}\n")
        wins = sum(1 for r in rows if r["actual_r_multiple"] > 0)
        f.write(f"Overall: win_rate={wins/len(rows):.1%} total_R={sum(r['actual_r_multiple'] for r in rows):+.1f} "
                f"expectancy_R={sum(r['actual_r_multiple'] for r in rows)/len(rows):+.3f}\n")

        print_table("By hypothesis type", bucket_stats(rows, lambda r: r["hypothesis_type"]), f)
        print_table("By confluence", bucket_stats(rows, lambda r: r["confluence"]), f)
        print_table("By direction", bucket_stats(rows, lambda r: r["direction"]), f)
        print_table("By type x confluence (the 'A setups' question)",
                     bucket_stats(rows, lambda r: f"{r['hypothesis_type']} / {r['confluence']}"), f)
        print_table("By day of week", bucket_stats(rows, lambda r: DAY_NAMES[r["day_of_week"]]), f)
        print_table("By hour (UTC-ish, source data's own clock)", bucket_stats(rows, lambda r: r["hour"]), f)
        print_table("By HTF conviction (counter-intraday trades only)",
                     bucket_stats([r for r in rows if r["hypothesis_type"].startswith("Counter")], lambda r: r["htf_conviction"]), f)
        print_table("By composite presence", bucket_stats(rows, lambda r: "has composite" if r["has_composite"] else "no composite"), f)

        def composite_zone(r):
            if not r["has_composite"]:
                return "n/a"
            p = r["position_in_composite"]
            if p <= 0.2:
                return "near VAL (bottom 20%)"
            if p >= 0.8:
                return "near VAH (top 20%)"
            return "mid-range"
        print_table("By position within nearest composite (fading-the-edge question)",
                     bucket_stats([r for r in rows if r["has_composite"]], composite_zone), f)

        # Single vs multi-target: how many captured hypotheses even have target_2/runner.
        n_multi = sum(1 for r in rows if r["target_2_price"] not in ("", None))
        f.write(f"\nMulti-target hypotheses (target_2 set): {n_multi:,} / {len(rows):,} "
                f"({n_multi/len(rows):.1%})\n")

        if sweep_path and sweep_path.exists():
            f.write("\n=== TP/SL/RRR sweep (sweep_exits.py) -- top 10 by total_R ===\n")
            with open(sweep_path, newline="") as sf:
                sweep_rows = list(csv.DictReader(sf))
            sweep_rows.sort(key=lambda r: -float(r["total_r"]))
            f.write(f"{'stop_mult':>10s} {'rrr':>6s} {'trades':>8s} {'win_rate':>9s} {'total_R':>10s} {'expectancy_R':>13s}\n")
            for r in sweep_rows[:10]:
                wr = float(r["win_rate"]) if r["win_rate"] else 0.0
                f.write(f"{r['stop_multiplier']:>10s} {r['rrr']:>6s} {r['trades']:>8s} {wr:9.1%} "
                        f"{float(r['total_r']):+10.1f} {float(r['expectancy_r'] or 0):+13.3f}\n")

            # Heatmap
            stop_mults = sorted(set(float(r["stop_multiplier"]) for r in sweep_rows))
            rrrs = sorted(set(float(r["rrr"]) for r in sweep_rows))
            grid = [[None] * len(rrrs) for _ in stop_mults]
            for r in sweep_rows:
                i = stop_mults.index(float(r["stop_multiplier"]))
                j = rrrs.index(float(r["rrr"]))
                grid[i][j] = float(r["total_r"])
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
            im = ax.imshow(grid, cmap="RdYlGn", aspect="auto")
            ax.set_xticks(range(len(rrrs)))
            ax.set_xticklabels(rrrs)
            ax.set_yticks(range(len(stop_mults)))
            ax.set_yticklabels(stop_mults)
            ax.set_xlabel("RRR (target = rrr x stop)")
            ax.set_ylabel("Stop multiplier (x structural risk)")
            ax.set_title("Total R by stop/RRR combination")
            for i in range(len(stop_mults)):
                for j in range(len(rrrs)):
                    ax.text(j, i, f"{grid[i][j]:+.0f}", ha="center", va="center", fontsize=8)
            fig.colorbar(im, ax=ax, label="Total R")
            fig.tight_layout()
            fig.savefig(out_dir / "sweep_heatmap.png")
            plt.close(fig)

    print(f"Done. Report: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
