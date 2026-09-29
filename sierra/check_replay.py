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
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REFERENCE = HERE / "reference_journal.csv"
TAIL_DAYS = 30

COLS = ["preset_id", "family", "signal_day", "entry_day", "exit_day", "side",
        "entry", "exit", "pnl_pts", "mae", "mfe", "bars", "reason"]


# Until the DayString() fix, the study wrote dates through sc.FormatDateTime(), which follows
# Sierra's global date/time display setting - so journals produced by an older build carry
# whatever format that machine was set to. Normalise the column so those can still be checked.
DAY_COLS = ["signal_day", "entry_day", "exit_day"]

# Anchored VWAP and its sigma bands are computed from volume. Sierra aggregates volume for the
# continuous contract its own way, so these families can disagree with the research data even
# when the logic is identical - unlike the price-only families, where a difference is a real bug.
VOLUME_FAMILIES = ("wvwap", "dvwap", "mvwap")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}$")
NUMERIC = re.compile(r"^(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})$")


def day_only(v: str) -> str:
    return (v or "").strip().split("T")[0].split(" ")[0]


def normalise_days(rows: list[dict], what: str):
    """Rewrite the day columns to YYYY-MM-DD in place, one decision for the whole file."""
    vals = [day_only(r[c]) for r in rows for c in DAY_COLS if day_only(r[c])]
    if all(ISO.match(v) for v in vals):
        for r in rows:
            for c in DAY_COLS:
                r[c] = day_only(r[c])
        return

    parts = []
    for v in vals:
        m = NUMERIC.match(v)
        if not m:
            raise SystemExit(f"{what} journal: cannot read the date {v!r}.\n"
                             f"  Rebuild the study - the current source writes YYYY-MM-DD - or send me the file.")
        parts.append([int(x) for x in m.groups()])

    # Year first is unambiguous. Otherwise day-first and month-first both parse, and guessing per
    # row silently mangles the first twelve days of a month, so decide from the whole column.
    if all(p[0] > 31 for p in parts):
        order = (0, 1, 2)
    elif any(p[0] > 12 for p in parts):
        order = (2, 1, 0)
    elif any(p[1] > 12 for p in parts):
        order = (2, 0, 1)
    else:
        raise SystemExit(f"{what} journal: the dates are ambiguous - {vals[0]!r} could be either\n"
                         f"  day-first or month-first, and nothing in the file settles it.\n"
                         f"  Rebuild the study (the current source writes YYYY-MM-DD) and replay again.")
    y, mo, d = order
    for r in rows:
        for c in DAY_COLS:
            v = day_only(r[c])
            if v:
                q = [int(x) for x in NUMERIC.match(v).groups()]
                r[c] = f"{q[y]:04d}-{q[mo]:02d}-{q[d]:02d}"
    print(f"  note: {what} journal dates were not ISO; read as "
          f"{'year' if y == 0 else 'day' if d == 0 else 'month'}-first and converted.")


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
    normalise_days(rows, what)
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
    # Positions still open when the Replay was stopped never reach the ledger, so the last few
    # sessions always look short on the replay side. Drop them rather than report them as a
    # difference - the average hold is about a week, so a month is comfortably clear of it.
    hi = (dt.date.fromisoformat(hi) - dt.timedelta(days=TAIL_DAYS)).isoformat()
    if lo > hi:
        raise SystemExit(
            f"\n  The journals do not overlap in time at all:\n"
            f"    replay  {min(r['entry_day'] for r in rep)} .. {max(r['entry_day'] for r in rep)}\n"
            f"    offline {min(r['entry_day'] for r in off)} .. {max(r['entry_day'] for r in off)}\n\n"
            f"  Either the Replay covered a period the reference does not reach, or the dates were\n"
            f"  read wrong. Send me the journal and I will look.")
    rep, off = window(rep, lo, hi), window(off, lo, hi)

    print(f"\n=== REPLAY vs OFFLINE ({lo} .. {hi}, last {TAIL_DAYS} days dropped) ===")
    summarise(rep, "replay")
    summarise(off, "offline")

    # Two checks that separate "the study traded differently" from "the day grid itself is wrong".
    # Both sides run the same code, so the set of days on which a signal can occur must be the
    # same set of RTH sessions. If it is not, nothing downstream is worth reading.
    rd = {r["entry_day"] for r in rep}
    od = {r["entry_day"] for r in off}
    weekend = sorted(d for d in rd
                     if dt.date.fromisoformat(d).weekday() >= 5)
    if weekend:
        print(f"\n  {len(weekend)} entries fall on a Saturday or Sunday, e.g. {', '.join(weekend[:3])}.\n"
              f"  The research day grid is RTH sessions, so this is a chart time-zone problem: entries\n"
              f"  are landing outside the session they belong to. Set the chart to New York (Eastern),\n"
              f"  or move RTH Start / RTH End by the same offset.")
    if len(rd) > 1.2 * len(od):
        print(f"\n  the replay signals on {len(rd)} distinct days against {len(od)} off-line, "
              f"{len(rd) / len(od):.1f}x as many.\n"
              f"  One calendar session is being finalised more than once - the study is seeing more\n"
              f"  'days' than there are sessions. Check 'Use specific session times' is OFF (the study\n"
              f"  needs the whole Globex session and cuts RTH itself) and that the chart is 1-minute.")

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

    shared = {r["entry_day"] for r in rep} & {r["entry_day"] for r in off}
    if not shared:
        rs, os_ = sorted({r["entry_day"] for r in rep}), sorted({r["entry_day"] for r in off})
        raise SystemExit(
            f"\n  The two journals do not share a single entry day, which no trading difference can\n"
            f"  produce. Something about the runs is not comparable at all.\n\n"
            f"    replay  entry days: {', '.join(rs[:4])} ... {rs[-1]}  ({len(rs)} days)\n"
            f"    offline entry days: {', '.join(os_[:4])} ... {os_[-1]}  ({len(os_)} days)\n\n"
            f"  Check, in this order:\n"
            f"    1. the chart's symbol - a Replay on a different instrument than ES\n"
            f"    2. the chart's time zone - a whole-session shift moves every entry a day\n"
            f"    3. that reference_journal.csv is the one committed next to this script")

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

    if diffs:
        fam_of = {r["preset_id"]: r["family"] for r in off}
        fam_of.update({r["preset_id"]: r["family"] for r in rep})
        by_fam: dict[str, list[int]] = {}
        for pid in ids:
            f = fam_of.get(pid, "?")
            d = next((x[0] for x in diffs if x[1] == pid), 0)
            by_fam.setdefault(f, [0, 0])
            by_fam[f][0] += d
            by_fam[f][1] += 1
        print("\n  by family, most days out first:")
        for f, (d, n) in sorted(by_fam.items(), key=lambda kv: -kv[1][0]):
            if d:
                vol = "  <- volume-dependent" if any(v in f for v in VOLUME_FAMILIES) else ""
                print(f"    {f:<22s}{d:5d} days out over {n} presets{vol}")
        vd = sum(d for f, (d, _) in by_fam.items() if any(v in f for v in VOLUME_FAMILIES))
        td = sum(d for _, (d, _) in by_fam.items())
        if td and vd / td > 0.5:
            print(f"\n  {100 * vd / td:.0f} % of the difference sits in the VWAP families, which are the ones\n"
                  f"  computed from volume. That points at Sierra's volume aggregation for the\n"
                  f"  continuous contract rather than at the trading logic - check that the chart\n"
                  f"  is Back Adjusted and that it is the same contract the research used.")

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
