"""
Parity test: run the ACSIL study off-line over real ES 1-minute bars and diff it against the
Python research engine, preset by preset.

This is step 2 of swing_lab/SIERRA_ARCHITECTURE.md done without Sierra Chart: the study is
compiled against test_stub/sierrachart.h, a minimal stand-in for the ACSIL API, so the whole
feature engine, preset parser, signal engine and ledger are exercised on the same data the
research used. It does NOT verify anything Sierra-specific (orders, chart drawing, session
handling by Sierra itself) - that still needs a Sierra Replay run.

usage: python run_parity.py [--from 2015-01-01] [--compare-from 2016-06-01]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE.parent / "swing_lab"
sys.path.insert(0, str(LAB))
TMP = Path("/tmp/claude-0/x") if Path("/tmp/claude-0/x").exists() else HERE / "build"


def build(tmp: Path):
    tmp.mkdir(parents=True, exist_ok=True)
    exe = tmp / "harness"
    cmd = ["g++", "-O2", "-std=c++17", f"-I{HERE / 'test_stub'}",
           str(HERE / "test_stub" / "harness.cpp"), str(HERE / "Lukacino_MultiSwing.cpp"), "-o", str(exe)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[:4000])
        raise SystemExit("compilation failed")
    return exe


def export_bars(tmp: Path, start: str):
    from data_prep import DATA
    out = tmp / "bars.csv"
    m = pd.read_parquet(DATA / "es1m_adj.parquet")
    m = m[m.index >= start]
    days = (m.index.normalize() - pd.Timestamp("1970-01-01")).days
    secs = m.index.hour * 3600 + m.index.minute * 60 + m.index.second
    pd.DataFrame({"days": days, "secs": secs, "o": m.Open.values, "h": m.High.values,
                  "l": m.Low.values, "c": m.Close.values, "v": m.Volume.values}).to_csv(out, index=False)
    return out, len(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2015-01-01")
    ap.add_argument("--compare-from", dest="cmp_from", default="2016-06-01")
    a = ap.parse_args()

    import systems as S
    from lab import Lab
    from sieve import RES

    exe = build(TMP)
    bars, n = export_bars(TMP, a.start)
    journal = TMP / "parity_journal.csv"
    journal.unlink(missing_ok=True)
    presets = RES / "swing_presets.csv"
    r = subprocess.run([str(exe), str(bars), str(presets), str(TMP / "parity_series.csv"), str(journal)],
                       capture_output=True, text=True)
    print(r.stderr.strip()[:2000])

    j = pd.read_csv(journal)
    j = j[j.entry_day >= a.cmp_from]
    pre = pd.read_csv(presets)
    lab = Lab()
    setups = {s[0]: s for s in S.setups(lab.d)}
    exits = {e[0]: e for e in S.exits(lab.d)}
    reg = S.regimes(lab.d)

    # ---- feature parity (daily bars, indicators, anchored VWAPs)
    h = pd.read_csv(TMP / "parity_series.csv")
    h["date"] = pd.Timestamp("1970-01-01") + pd.to_timedelta(h.days, "D")
    last = h.groupby("days").tail(1).set_index("date")
    d = lab.d
    cmp_cols = [("daily_close", "close", "daily close"), ("atr20", "atr20", "ATR20"),
                ("wvwap", "wvwap", "weekly VWAP"), ("mvwap", "mvwap", "monthly VWAP"),
                ("rsi2", "rsi2", "RSI2"), ("ibs", "ibs", "IBS"), ("connors", "connors_rsi", "ConnorsRSI"),
                ("wsd", "wvwap_sd", "weekly sigma"), ("dsd", "dvwap_sd", "daily sigma")]
    jj = pd.concat([last[[c for c, _, _ in cmp_cols]], d[[p for _, p, _ in cmp_cols]].add_suffix("_py")], axis=1).dropna()
    jj = jj[(jj.index >= a.cmp_from) & (jj.daily_close > 0)]
    print(f"\n=== FEATURE PARITY ({len(jj)} days) ===")
    for cc, pp, nm in cmp_cols:
        e = (jj[cc] - jj[pp + "_py"]).abs()
        print(f"  {nm:<14s} median {e.median():.5f}  p95 {e.quantile(.95):.5f}")
    print("  (a handful of large outliers are shortened sessions, where the study finalises the day "
          "at the next session's first bar and this comparison samples the calendar day)")

    # ---- trade parity, preset by preset
    rows = []
    for rr in pre.itertuples():
        cfg = S.build_cfg(lab.d, setups[rr.setup], exits[rr.exit], 1, reg[rr.regime], 0.0)
        _, _, t = lab.run(cfg, full=True)
        t = t[t.entry_day >= a.cmp_from]
        c = j[j.preset_id == rr.id]
        pe = set(pd.to_datetime(t.entry_day).dt.strftime("%Y-%m-%d"))
        ce = set(c.entry_day)
        rows.append(dict(id=rr.id, exit=rr.exit, py=len(t), cpp=len(c),
                         only_cpp=len(ce - pe), only_py=len(pe - ce),
                         py_pnl=round(t.pnl_pts.sum()), cpp_pnl=round(c.pnl_pts.sum())))
    df = pd.DataFrame(rows)
    df["diff"] = df.only_cpp + df.only_py
    tol = np.maximum(2, 0.03 * df.py)
    print(f"\n=== TRADE PARITY ({len(df)} presets, from {a.cmp_from}) ===")
    print(df[df["diff"] > tol].to_string(index=False))
    print(f"\n  identical entry sets      : {int((df['diff'] == 0).sum())}/{len(df)}")
    print(f"  >= 97 % entry overlap     : {int((df['diff'] <= tol).sum())}/{len(df)}")
    print(f"  trades   python {df.py.sum()}  study {df.cpp.sum()}")
    print(f"  P&L pts  python {df.py_pnl.sum():.0f}  study {df.cpp_pnl.sum():.0f} "
          f"({100 * df.cpp_pnl.sum() / df.py_pnl.sum():.1f} %)")
    print("\n  The study is intentionally the more pessimistic of the two: it resolves a stop and a "
          "target inside one session on the daily range with the stop first, while the research "
          "engine walks 30-minute bars. Live P&L below the backtest is the expected direction.")
    df.to_csv(RES / "parity_report.csv", index=False)


if __name__ == "__main__":
    main()
