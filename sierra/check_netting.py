"""
What the account actually earns when 48 presets are traded as one net position.

The study holds one chart position and moves it to what the book wants, once per session. A preset
that stops out intraday and another that enters the same day cancel, so no order is sent - and the
position that "stopped out" was never actually closed. 39 % of the book's exits happen at a stop, a
target or a trail, none of them at the session close the sync trades at.

This replays both: the ledger, where every preset exits at its own price, and the netted account,
which only ever changes size at a session close. They are not the same strategy, so the difference
is not slippage to be tuned away - it is the cost of the design, and it belongs on the table before
the thing trades.

usage:
    python check_netting.py [--journal sierra/reference_journal.csv]
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "swing_lab"))

INTRADAY_EXITS = ("sl", "tp", "trail", "breakeven")


def curve_stats(daily: np.ndarray):
    eq = np.cumsum(daily)
    dd = eq - np.maximum.accumulate(eq)
    return eq[-1], dd.min(), daily.min()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=str(HERE / "reference_journal.csv"))
    ap.add_argument("--from", dest="lo", default="2016-06-01")
    ap.add_argument("--to", dest="hi", default="2026-09-23")
    a = ap.parse_args()

    from lab import Lab
    d = Lab().d
    close = d["close"].values
    idx = {x.strftime("%Y-%m-%d"): i for i, x in enumerate(d.index)}

    rows = [r for r in csv.DictReader(open(a.journal))
            if a.lo <= r["entry_day"] <= a.hi]
    for r in rows:
        r["pnl_pts"] = float(r["pnl_pts"])

    # Contracts held into each session, which is what the sync leaves the account holding.
    pos = collections.Counter()
    for r in rows:
        i, j = idx.get(r["entry_day"]), idx.get(r["exit_day"])
        if i is None or j is None:
            continue
        for k in range(i, j):
            pos[k] += 1

    n = len(close)
    account = np.zeros(n)
    ledger = np.zeros(n)
    for k in range(n - 1):
        account[k + 1] = pos[k] * (close[k + 1] - close[k])
    for r in rows:
        j = idx.get(r["exit_day"])
        if j is not None:
            ledger[j] += r["pnl_pts"]

    print(f"\n=== LEDGER vs NETTED ACCOUNT ({a.lo} .. {a.hi}, 1 contract per preset) ===\n")
    print(f"  {'':<24s}{'P&L':>9s}{'max DD':>10s}{'P&L/DD':>9s}{'worst day':>11s}")
    for name, series in (("ledger, 48 exits", ledger), ("netted account", account)):
        pnl, dd, worst = curve_stats(series)
        print(f"  {name:<24s}{pnl:9.0f}{dd:10.0f}{abs(pnl / dd):9.2f}{worst:11.0f}")

    intraday = sum(1 for r in rows if r["reason"] in INTRADAY_EXITS)
    print(f"\n  peak position {max(pos.values())} contracts")
    print(f"  {intraday} of {len(rows)} exits ({100 * intraday / len(rows):.0f} %) happen at a stop,\n"
          f"  target or trail rather than at the session close, so the netted account never makes\n"
          f"  those trades at all: it carries the position through and takes whatever follows.")


if __name__ == "__main__":
    main()
