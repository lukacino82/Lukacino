"""
Diff a Sierra Chart Replay journal against the off-line harness journal, preset by preset.

`run_parity.py` proves the study's logic matches the Python research engine. It cannot prove
anything about Sierra itself: session boundaries, contract rollover, bar ordering, and whether
the study computes the same numbers when bars arrive one at a time instead of all at once.

A Replay run exercises exactly that. Since the Replay and the harness run the *same* C++ code
over the *same* instrument, their journals should be near identical on the overlapping window.
Every difference is Sierra-specific and therefore worth looking at.

usage:
    python check_replay.py swing_journal.csv

Runs on a stock Python 3.8+, no packages to install: the off-line side is committed as
reference_journal.csv, so this works on the machine Sierra runs on, without a compiler and
without the market data. --rebuild regenerates that reference from the current study source
and does need the research environment, so in practice it only runs in the repo.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REFERENCE = HERE / "reference_journal.csv"

COLS = ["preset_id", "family", "signal_day", "entry_day", "exit_day", "side",
        "entry", "exit", "pnl_pts", "mae", "mfe", "bars", "reason"]


def load_journal(path: Path, what: str) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"{what} journal not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{what} journal is empty.")
    missing = [c for c in COLS if c not in rows[0]]
    if missing:
        raise SystemExit(f"{what} journal is missing columns {missing}.\n"
                         f"Expected the ledger written by Lukacino_MultiSwing: {', '.join(COLS)}")
    for r in rows:
        r["pnl_pts"] = float(r["pnl_pts"] or 0)
    return rows


def build_offline() -> Path:
    """Regenerate the reference ledger. Needs g++, pandas and the research data."""
    from run_parity import TMP, build, export_bars
    from sieve import RES
    exe = build(TMP)
    bars, n = export_bars(TMP, "2015-01-01")
    print(f"  harness: {n} bars exported, running ...")
    journal = TMP / "parity_journal.csv"
    journal.unlink(missing_ok=True)
    r = subprocess.run([str(exe), str(bars), str(RES / "swing_presets.csv"),
                        str(TMP / "parity_series.csv"), str(journal)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[:2000])
        raise SystemExit("harness run failed")
    return journal


def window(rows: list[dict], lo: str, hi: str) -> list[dict]:
    return [r for r in rows if lo <= r["entry_day"] <= hi]


def summarise(rows: list[dict], label: str):
    print(f"  {label:<8s}{len(rows):5d} trades {sum(r['pnl_pts'] for r in rows):9.0f} pts   "
          f"{len({r['preset_id'] for r in rows})} presets, {len({r['family'] for r in rows})} families")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay", help="swing_journal.csv written by the study during Replay")
    ap.add_argument("--offline", default=None,
                    help=f"journal to diff against (default: {REFERENCE.name})")
    ap.add_argument("--rebuild", action="store_true",
                    help="regenerate the reference journal from the current study source")
    ap.add_argument("--top", type=int, default=15, help="how many worst presets to list")
    a = ap.parse_args()

    rep = load_journal(Path(a.replay), "replay")
    if a.offline:
        off_path = Path(a.offline)
    elif a.rebuild or not REFERENCE.exists():
        off_path = build_offline()
    else:
        off_path = REFERENCE
    off = load_journal(off_path, "offline")

    # The replay warms the indicators up before it can signal, so its own first entry sets the
    # window. The tail is whichever run stops first.
    lo = min(r["entry_day"] for r in rep)
    hi = min(max(r["entry_day"] for r in rep), max(r["entry_day"] for r in off))
    rep, off = window(rep, lo, hi), window(off, lo, hi)

    print(f"\n=== REPLAY vs OFFLINE ({lo} .. {hi}) ===")
    summarise(rep, "replay")
    summarise(off, "offline")

    ids = sorted({r["preset_id"] for r in rep} | {r["preset_id"] for r in off})
    silent = sorted({r["preset_id"] for r in off} - {r["preset_id"] for r in rep})
    if silent:
        print(f"\n  presets that never fired in the replay ({len(silent)}): {', '.join(silent)}")

    diffs, n_same, n_close, pnl_r, pnl_o = [], 0, 0, 0.0, 0.0
    for pid in ids:
        r = [x for x in rep if x["preset_id"] == pid]
        o = [x for x in off if x["preset_id"] == pid]
        re_, oe = {x["entry_day"] for x in r}, {x["entry_day"] for x in o}
        only_r, only_o = len(re_ - oe), len(oe - re_)
        pr, po = sum(x["pnl_pts"] for x in r), sum(x["pnl_pts"] for x in o)
        pnl_r += pr
        pnl_o += po
        n_same += (only_r + only_o) == 0
        n_close += (only_r + only_o) <= max(1, 0.01 * len(o))
        if only_r or only_o:
            diffs.append((only_r + only_o, pid, len(r), len(o), only_r, only_o, pr, po))

    print(f"\n  identical entry sets      : {n_same}/{len(ids)}")
    print(f"  >= 99 % entry overlap     : {n_close}/{len(ids)}")

    if diffs:
        print(f"\n  presets that differ ({len(diffs)}), worst first:")
        head = f"  {'id':<18s}{'replay':>7s}{'offline':>8s}{'only_rep':>9s}{'only_off':>9s}{'rep_pnl':>9s}{'off_pnl':>9s}"
        print(head)
        for d, pid, nr, no, orr, oo, pr, po in sorted(diffs, reverse=True)[:a.top]:
            print(f"  {pid:<18s}{nr:>7d}{no:>8d}{orr:>9d}{oo:>9d}{pr:>9.0f}{po:>9.0f}")

    if pnl_o:
        print(f"\n  P&L pts  replay {pnl_r:.0f}  offline {pnl_o:.0f} ({100 * pnl_r / pnl_o:.1f} %)")

    if not diffs:
        print("\n  Identical. Sierra's session handling, rollover and bar-by-bar delivery match the\n"
              "  off-line run, so the parity already measured against Python carries over to Replay.")
    else:
        print("\n  The two runs execute the same C++ over the same instrument, so every difference is\n"
              "  Sierra-specific. Usual causes, in order of likelihood: the chart is not Back Adjusted,\n"
              "  the chart's time zone is not New York, 'Use specific session times' is on, or Days to\n"
              "  Load cut the history short. Check those before suspecting the study.")


if __name__ == "__main__":
    main()
