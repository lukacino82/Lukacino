"""
Diff a Sierra Chart Replay journal against the off-line harness journal, preset by preset.

`run_parity.py` proves the study's logic matches the Python research engine. It cannot prove
anything about Sierra itself: session boundaries, contract rollover, bar ordering, and whether
the study computes the same numbers when bars arrive one at a time instead of all at once.

A Replay run exercises exactly that. Since the Replay and the harness run the *same* C++ code
over the *same* instrument, their journals should be near identical on the overlapping window.
Every difference is Sierra-specific and therefore worth looking at.

usage:
    python check_replay.py swing_journal.csv [--offline build/parity_journal.csv] [--top 15]

Without --offline the harness is compiled and run first, which takes a few minutes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

COLS = ["preset_id", "family", "signal_day", "entry_day", "exit_day", "side",
        "entry", "exit", "pnl_pts", "mae", "mfe", "bars", "reason"]


def load_journal(path: Path, what: str) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"{what} journal not found: {path}")
    j = pd.read_csv(path)
    missing = [c for c in COLS if c not in j.columns]
    if missing:
        raise SystemExit(f"{what} journal is missing columns {missing}.\n"
                         f"Expected the ledger written by Lukacino_MultiSwing: {', '.join(COLS)}")
    if j.empty:
        raise SystemExit(f"{what} journal is empty.")
    return j


def build_offline() -> Path:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay", help="swing_journal.csv written by the study during Replay")
    ap.add_argument("--offline", default=None, help="harness journal; built on the fly when omitted")
    ap.add_argument("--top", type=int, default=15, help="how many worst presets to list")
    a = ap.parse_args()

    rep = load_journal(Path(a.replay), "replay")
    off_path = Path(a.offline) if a.offline else build_offline()
    off = load_journal(off_path, "offline")

    # The replay warms the indicators up before it can signal, so its own first entry sets the
    # window. The tail is whichever run stops first.
    lo = rep.entry_day.min()
    hi = min(rep.entry_day.max(), off.entry_day.max())
    rep = rep[(rep.entry_day >= lo) & (rep.entry_day <= hi)]
    off = off[(off.entry_day >= lo) & (off.entry_day <= hi)]
    print(f"\n=== REPLAY vs OFFLINE ({lo} .. {hi}) ===")
    print(f"  replay  {len(rep):5d} trades   {rep.pnl_pts.sum():8.0f} pts   "
          f"{rep.preset_id.nunique()} presets, {rep.family.nunique()} families")
    print(f"  offline {len(off):5d} trades   {off.pnl_pts.sum():8.0f} pts   "
          f"{off.preset_id.nunique()} presets, {off.family.nunique()} families")

    silent = sorted(set(off.preset_id) - set(rep.preset_id))
    if silent:
        print(f"\n  presets that never fired in the replay ({len(silent)}): {', '.join(silent)}")

    rows = []
    for pid in sorted(set(off.preset_id) | set(rep.preset_id)):
        r, o = rep[rep.preset_id == pid], off[off.preset_id == pid]
        re_, oe = set(r.entry_day), set(o.entry_day)
        rows.append(dict(id=pid, replay=len(r), offline=len(o),
                         only_replay=len(re_ - oe), only_offline=len(oe - re_),
                         replay_pnl=r.pnl_pts.sum(), offline_pnl=o.pnl_pts.sum()))
    df = pd.DataFrame(rows)
    df["diff"] = df.only_replay + df.only_offline

    print(f"\n  identical entry sets      : {int((df['diff'] == 0).sum())}/{len(df)}")
    print(f"  >= 99 % entry overlap     : "
          f"{int((df['diff'] <= (0.01 * df.offline).clip(lower=1)).sum())}/{len(df)}")
    worst = df[df['diff'] > 0].sort_values("diff", ascending=False)
    if len(worst):
        print(f"\n  presets that differ ({len(worst)}), worst first:")
        print(worst.head(a.top).to_string(index=False))

    pnl_r, pnl_o = df.replay_pnl.sum(), df.offline_pnl.sum()
    print(f"\n  P&L pts  replay {pnl_r:.0f}  offline {pnl_o:.0f} "
          f"({100 * pnl_r / pnl_o:.1f} %)" if pnl_o else "")

    if df["diff"].sum() == 0:
        print("\n  Identical. Sierra's session handling, rollover and bar-by-bar delivery match the\n"
              "  off-line run, so the parity already measured against Python carries over to Replay.")
    else:
        print("\n  The two runs execute the same C++ over the same instrument, so every difference is\n"
              "  Sierra-specific. Usual causes, in order of likelihood: the chart is not Back Adjusted,\n"
              "  the chart's time zone is not New York, 'Use specific session times' is on, or Days to\n"
              "  Load cut the history short. Check those before suspecting the study.")


if __name__ == "__main__":
    main()
