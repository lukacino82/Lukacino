"""
Diff the study's per-day feature dump against the research engine, column by column.

check_replay.py compares trades, which is the outcome. When those differ and the rules are
identical, the cause is in the numbers the rules were given, and this says which number: the day's
volume, the anchored VWAPs built from it, or the price-only indicators.

The distinction matters because it decides who has to change. A price column that disagrees is the
study's arithmetic. Volume that disagrees is Sierra's aggregation of the continuous contract
against the research dataset, and no amount of work on the study will reconcile it.

usage:
    python check_features.py swing_features.csv        # in the repo, with the research data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "swing_lab"))

# study column -> research column. Left out: sigma bands, which are compared through the VWAPs.
PAIRS = [
    ("close", "close", "daily close"), ("volume", "volume", "day volume"),
    ("atr20", "atr20", "ATR20"), ("dvwap", "dvwap", "daily VWAP"),
    ("wvwap", "wvwap", "weekly VWAP"), ("mvwap", "mvwap", "monthly VWAP"),
    ("wvwap_sd", "wvwap_sd", "weekly sigma"), ("dvwap_sd", "dvwap_sd", "daily sigma"),
    ("rsi2", "rsi2", "RSI2"), ("ibs", "ibs", "IBS"), ("connors", "connors_rsi", "ConnorsRSI"),
    ("sma5", "sma5", "SMA5"), ("sma200", "sma200", "SMA200"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", help="the CSV written by the study's 'Feature Dump CSV' input")
    ap.add_argument("--tol", type=float, default=0.001, help="relative tolerance for 'agrees'")
    a = ap.parse_args()

    from lab import Lab
    d = Lab().d
    s = pd.read_csv(a.dump, parse_dates=["day"]).set_index("day").sort_index()
    both = s.index.intersection(d.index)
    if len(both) == 0:
        raise SystemExit("the dump and the research data share no day at all - check the dates")
    s, r = s.loc[both], d.loc[both]
    print(f"\n=== FEATURES, STUDY vs RESEARCH ({len(both)} days, "
          f"{both.min():%Y-%m-%d} .. {both.max():%Y-%m-%d}) ===\n")
    print(f"  {'column':<16s}{'median rel':>12s}{'p95 rel':>10s}{'worst day':>14s}{'agrees':>9s}")

    for sc, rc, name in PAIRS:
        if sc not in s.columns or rc not in r.columns:
            continue
        x, y = s[sc].astype(float), r[rc].astype(float)
        scale = y.abs().replace(0, np.nan)
        e = ((x - y).abs() / scale).dropna()
        if e.empty:
            continue
        worst = e.idxmax()
        print(f"  {name:<16s}{e.median():12.6f}{e.quantile(.95):10.6f}"
              f"{worst:%Y-%m-%d}{100 * (e <= a.tol).mean():8.0f} %")

    # Volume is the one input the study cannot be right about on its own, so it gets its own verdict.
    if "volume" in s.columns and "volume" in r.columns:
        v = (s.volume.astype(float) - r.volume.astype(float)).abs() / r.volume.replace(0, np.nan)
        med = v.median()
        print()
        if med <= a.tol:
            print(f"  Volume agrees to {med:.4%} at the median, so the VWAPs are built from the same\n"
                  f"  input as the research and any VWAP difference above is the study's own.")
        else:
            print(f"  Volume differs by {med:.2%} at the median. The anchored VWAPs and their sigma\n"
                  f"  bands are volume-weighted, so they inherit this and the VWAP families will\n"
                  f"  keep entering on slightly different days no matter what the study does. This\n"
                  f"  is Sierra's aggregation of the continuous contract against the research\n"
                  f"  dataset, not a bug to fix in the study.")


if __name__ == "__main__":
    main()
