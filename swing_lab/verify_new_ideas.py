"""
Check the ES2008 lower-close / VWAP swing claims against the raw data, from scratch.

The claims come from README_SIERRA_ES2008_SWING_ALPHA.md and
ES2008_LOWER_CLOSE_VWAP_MASTER_REPORT.html: a set of systems reported at PF 1.6-19 and, for the
monthly one, a 100 % win rate. None of them is compared against the only benchmark that matters
for a long-only system on an index that drifts up - holding the same instrument for the same
number of days. This script runs that comparison, and it runs it on the same 6,439,576 minute
rows the report used, so the numbers are directly comparable rather than approximate.

Three tests, in order of what they settle:

  1. reproduce  - do the reported trade counts and net points come out of this data at all?
                  If they do not, nothing else is worth reading.
  2. placebo    - same number of entries, same holding period, entry days drawn at random.
                  A system that cannot beat that is measuring the index, not a signal.
  3. look-ahead - "exact finalized streak of 3" is only known once a 4th session closes >= the
                  3rd. Entering the morning after the 3rd therefore uses a close that has not
                  happened. Both readings are run side by side.

usage:
    python verify_new_ideas.py [--data ES2008.txt] [--cache daily.csv] [--reps 10000]

Needs pandas and numpy, and ES2008.txt - the 483 MB file inside the multipart ES2008 archive in
the repo root. Combine it with:  cat ES2008.z01 ES2008.z02 ES2008.z03 ES2008.z04 ES2008.zip > all.zip
then unzip all.zip (unzip warns about the offset and re-compensates; the result is byte-exact).
The daily grid is cached, so only the first run pays the parse.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

FRICTION = 0.5      # the report's 0.5 ES point round trip
MAXH = 20           # the report's maximum holding period, in RTH sessions


def build_daily(src: Path, cache: Path) -> pd.DataFrame:
    """RTH 09:30-16:00 daily bars with day/week/month VWAP, the grid the research runs on."""
    if cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    df = pd.read_csv(src, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    ts = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip(), format="%Y/%m/%d %H:%M:%S")
    mins = ts.dt.hour * 60 + ts.dt.minute
    rth = df[(mins >= 9 * 60 + 30) & (mins < 16 * 60)].copy()
    rth["day"] = ts[rth.index].dt.normalize()
    rth["tpv"] = (rth["High"] + rth["Low"] + rth["Last"]) / 3.0 * rth["Volume"]

    g = rth.groupby("day")
    d = pd.DataFrame({"open": g["Open"].first(), "high": g["High"].max(), "low": g["Low"].min(),
                      "close": g["Last"].last(), "vol": g["Volume"].sum(), "tpv": g["tpv"].sum()})
    d = d[d["vol"] > 0]
    d.index = pd.DatetimeIndex(d.index)
    d["dvwap"] = d["tpv"] / d["vol"]
    # week- and month-to-date VWAP, valued at each session
    for tag, per in (("w", d.index.to_period("W")), ("m", d.index.to_period("M"))):
        d[f"{tag}vwap"] = d.groupby(per)["tpv"].cumsum() / d.groupby(per)["vol"].cumsum()
    d["wk"], d["mo"] = d.index.to_period("W").astype(str), d.index.to_period("M").astype(str)
    d["sma200"] = d["close"].rolling(200).mean()
    d["sma200w"] = d["close"].rolling(200).mean()      # ~40 weeks of sessions
    d["sma210"] = d["close"].rolling(210).mean()       # ~10 months of sessions
    lower = d["close"] < d["close"].shift()
    d["downdays"] = lower.groupby((~lower).cumsum()).cumsum()
    d.to_csv(cache)
    return d


class Book:
    """One position at a time: enter at the next RTH open, exit on target, stop or time."""

    def __init__(self, d: pd.DataFrame):
        self.o, self.h, self.l, self.c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.n = len(d)

    def trade(self, s: int, target: float, stop_pts: float, hold: int = MAXH):
        """Gap-through fills at the actual open; a bar touching both resolves as the stop, as the
        study does. Returns (points, sessions held)."""
        entry = self.o[s + 1]
        stop = entry - stop_pts if stop_pts > 0 else -1e18
        for k in range(s + 1, min(s + 1 + hold, self.n)):
            if self.o[k] <= stop:
                return self.o[k] - entry - FRICTION, k - s
            if self.l[k] <= stop:
                return stop - entry - FRICTION, k - s
            if self.h[k] >= target:
                return target - entry - FRICTION, k - s
        j = min(s + hold, self.n - 1)
        return self.c[j] - entry - FRICTION, j - s

    def hold_only(self, s: int, hold: int) -> float:
        """No target, no stop: the honest benchmark for a long-only index system."""
        return self.c[min(s + hold, self.n - 1)] - self.o[s + 1] - FRICTION

    def sequence(self, days, hold: int):
        """Non-overlapping, so the trade count matches how the report counts them."""
        out, busy = [], -1
        for s in days:
            if s <= busy or s + 1 >= self.n:
                continue
            if s + hold >= self.n:
                break
            out.append(self.hold_only(s, hold))
            busy = s + hold
        return np.array(out)


def stats(p: np.ndarray) -> tuple[float, float]:
    win, loss = p[p > 0].sum(), -p[p < 0].sum()
    return (win / loss if loss > 0 else float("inf")), 100.0 * (p > 0).mean()


def test_reproduce_and_placebo(d: pd.DataFrame, reps: int, rng) -> None:
    b = Book(d)
    c = d.close
    sigs = {
        "S01 streak 3-6 + bull + <dVWAP, hold 20": (d.downdays.between(3, 6) & (c > d.sma200) & (c < d.dvwap), 20),
        "S10 close < daily VWAP, hold 10":         (c < d.dvwap, 10),
        "S11 < daily VWAP + > MA200, hold 20":     ((c < d.dvwap) & (c > d.sma200), 20),
        "S20 weekly < wVWAP + MA40, hold 65":      ((d.wk != d.wk.shift(-1)) & (c < d.wvwap) & (c > d.sma200w), 65),
        "S30 monthly < mVWAP + MA10, hold 126":    ((d.mo != d.mo.shift(-1)) & (c < d.mvwap) & (c > d.sma210), 126),
        "exact 3 lower closes, hold 20":           (d.downdays == 3, 20),
        "exact 4 lower closes, hold 20":           (d.downdays == 4, 20),
    }
    print("\n=== 1+2. the reported systems, and the same bet placed on random days ===\n")
    print(f"{'system':<40s}{'n':>4s}{'total':>8s}{'per trade':>10s}{'PF':>7s}{'WR':>7s}"
          f"{'random median':>15s}{'p':>7s}")
    for name, (sig, hold) in sigs.items():
        p = b.sequence(np.flatnonzero(sig.to_numpy()), hold)
        if len(p) == 0:
            print(f"{name:<40s} no trades")
            continue
        pf, wr = stats(p)
        lo, hi = 1, b.n - hold - 1
        draws = np.array([np.sum([b.hold_only(s, hold) for s in rng.integers(lo, hi, len(p))])
                          for _ in range(reps)])
        print(f"{name:<40s}{len(p):>4d}{p.sum():>8.0f}{p.mean():>10.1f}{pf:>7.2f}{wr:>6.1f}%"
              f"{np.median(draws):>15.0f}{(draws >= p.sum()).mean():>7.3f}")
    print("\n  p is the share of random-entry runs that matched or beat the system. A system whose\n"
          "  p is not small is not a signal: it is the index, sampled a different way.")


def test_lookahead(d: pd.DataFrame) -> None:
    b = Book(d)
    c, dn = d.close.to_numpy(float), d.downdays.to_numpy()

    def episodes(k: int):
        """Maximal streaks of exactly k - the report's 'exact finalized streak'. Knowing a streak
        stopped at k requires the next close, which is why the entry offset below matters."""
        return [s for s in np.flatnonzero(dn == k) if s + 1 < b.n and c[s + 1] >= c[s]]

    def run(days, k: int, stop_pts: float, offset: int):
        out, busy = [], -1
        for s0 in days:
            s = s0 + offset
            if s <= busy or s + 1 >= b.n - 1:
                continue
            target = c[s0 - k]                      # the close before the streak began
            if b.o[s + 1] >= target:                # already recovered: no trade to take
                continue
            p, bars = b.trade(s, target, stop_pts)
            out.append(p)
            busy = s + bars
        return np.array(out)

    print("\n=== 3. the same rule read two ways ===\n")
    print(f"{'':<56s}{'n':>4s}{'total':>8s}{'per trade':>11s}{'PF':>7s}{'WR':>7s}")
    for k, stop in ((3, 20), (3, 25), (4, 10), (4, 150), (5, 15)):
        eps = episodes(k)
        for offset, tag in ((0, "as reported (uses tomorrow's close)"),
                            (1, "tradable (after confirmation)")):
            p = run(eps, k, stop, offset)
            if len(p) == 0:
                continue
            pf, wr = stats(p)
            label = f"{k} lower closes, SL {stop}p, {tag}"
            print(f"{label:<56s}{len(p):>4d}{p.sum():>8.0f}{p.mean():>11.2f}{pf:>7.2f}{wr:>6.1f}%")
        print()
    print("  The reported win rates (51.2 % for 3 lower / SL 20, 34.6 % for 5 lower / SL 15) match\n"
          "  the first line of each pair, so that is the entry the report measured. The second line\n"
          "  is the same rule once the confirming close has actually printed.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ES2008.txt")
    ap.add_argument("--cache", default="es2008_daily.csv")
    ap.add_argument("--reps", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    src, cache = Path(a.data), Path(a.cache)
    if not cache.exists() and not src.exists():
        raise SystemExit(f"{src} not found. See this file's docstring for how to unpack it.")
    d = build_daily(src, cache)
    bh = d.close.iloc[-1] - d.close.iloc[0]
    print(f"{len(d)} RTH sessions, {d.index[0].date()} .. {d.index[-1].date()}")
    print(f"buy & hold, one contract, always in: {bh:,.2f} pts "
          f"({bh / len(d):.2f} pts per session held)")
    rng = np.random.default_rng(a.seed)
    test_reproduce_and_placebo(d, a.reps, rng)
    test_lookahead(d)


if __name__ == "__main__":
    main()
