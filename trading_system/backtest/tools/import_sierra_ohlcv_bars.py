"""Converts Sierra-Chart-exported 1-minute OHLCV bars (Date, Time, Open, High,
Low, Last, Volume, NumberOfTrades, BidVolume, AskVolume) into this repo's
bridge CSV shapes (daily_profile_export.csv + historical_intraday.csv), so
run_backtest.py can run against real historical data instead of only live
ACSIL-captured history.

Nothing in trading_system computes VWAP/SD-bands/delta/volume-profile from
raw bars today -- ACSIL's own studies always did that inside Sierra Chart.
This reimplements the same quantities in Python, documented inline, so the
approximations are visible rather than silently assumed correct:

  - VWAP (intraday/weekly/monthly): cumulative volume-weighted average of
    each bar's typical price (H+L+Last)/3, reset at the start of each
    session/week/month. "Session" = the file's own Date column value, not a
    custom trading-day boundary.
  - SD1 bands: cumulative volume-weighted standard deviation of typical
    price around the running VWAP (same reset boundaries).
  - cum_delta: running sum of (AskVolume - BidVolume) per bar (ask-side =
    buyer-initiated, bid-side = seller-initiated -- standard footprint
    convention), reset every session.
  - Daily VAL/VAH/POC: a volume-at-price histogram per session, binned to
    the instrument's tick_size, POC = the bin with the most volume, VAL/VAH
    = the boundaries of the smallest contiguous price range (built by
    repeatedly adding whichever neighboring bin has more volume) holding
    >=70% of the session's volume -- the standard Market Profile value-area
    algorithm.

Usage:
    python3 convert.py <input.txt> <tick_size> <out_dir>
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime


def iso_week_key(y: int, m: int, d: int) -> tuple:
    iso = datetime(y, m, d).isocalendar()
    return (iso[0], iso[1])


class RunningVWAP:
    __slots__ = ("pv", "vol", "pv2")

    def __init__(self) -> None:
        self.pv = 0.0
        self.vol = 0.0
        self.pv2 = 0.0

    def add(self, price: float, vol: float) -> None:
        self.pv += price * vol
        self.vol += vol
        self.pv2 += vol * price * price

    def vwap(self) -> float:
        return self.pv / self.vol if self.vol > 0 else 0.0

    def sd1_distance(self) -> float:
        """The distance from vwap to its +1 SD band -- what ACSIL's
        vwap_*_sd1 field actually holds (a distance, not a price level; see
        LiveMarketState's own field docstring -- the ACSIL C++ side even
        names its variable *Distance). Fixed after a real backtest run
        surfaced this: treating it as a price level made tier_report's
        tolerance calculation wildly too large.
        """
        if self.vol <= 0:
            return 0.0
        mean = self.pv / self.vol
        var = self.pv2 / self.vol - mean * mean
        if var < 0:
            var = 0.0
        return var ** 0.5


def value_area(hist: dict, total_vol: float, tick: float) -> tuple:
    """Standard Market Profile VAL/VAH/POC from a price(tick-rounded)->volume histogram."""
    if not hist:
        return (0.0, 0.0, 0.0)
    poc_price = max(hist, key=lambda p: hist[p])
    prices_sorted = sorted(hist)
    idx = {p: i for i, p in enumerate(prices_sorted)}
    lo = hi = idx[poc_price]
    included = hist[poc_price]
    target = total_vol * 0.70
    while included < target and (lo > 0 or hi < len(prices_sorted) - 1):
        below = hist.get(prices_sorted[lo - 1], 0.0) if lo > 0 else -1.0
        above = hist.get(prices_sorted[hi + 1], 0.0) if hi < len(prices_sorted) - 1 else -1.0
        if above >= below:
            hi += 1
            included += hist[prices_sorted[hi]]
        else:
            lo -= 1
            included += hist[prices_sorted[lo]]
    return (prices_sorted[lo], prices_sorted[hi], poc_price)


def main() -> None:
    in_path, tick_size_s, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    tick_size = float(tick_size_s)
    instrument = "ES"

    intraday = RunningVWAP()
    weekly = RunningVWAP()
    monthly = RunningVWAP()
    cum_delta = 0.0
    session_open = None
    cur_day = None
    cur_week = None
    cur_month = None
    day_hist: dict = defaultdict(float)
    day_vol = 0.0

    daily_rows = []

    with open(in_path, newline="") as f, open(f"{out_dir}/historical_intraday.csv", "w", newline="") as out_f:
        reader = csv.reader(f)
        header = next(reader)
        writer = csv.writer(out_f)
        writer.writerow([
            "timestamp", "instrument", "last_price", "session_open",
            "vwap_monthly", "vwap_weekly", "vwap_intraday", "cum_delta",
            "vwap_intraday_sd1", "vwap_monthly_sd1", "vwap_weekly_sd1",
        ])
        n = 0
        for row in reader:
            if len(row) < 10:
                continue
            date_s, time_s, o, h, l, last, vol, ntrades, bidvol, askvol = (x.strip() for x in row[:10])
            y, mo, d = (int(x) for x in date_s.split("/"))
            hh, mm, ss = (int(x) for x in time_s.split(":"))
            o, h, l, last = float(o), float(h), float(l), float(last)
            vol = float(vol)
            bidvol, askvol = float(bidvol), float(askvol)
            typical = (h + l + last) / 3.0

            day_key = (y, mo, d)
            week_key = iso_week_key(y, mo, d)
            month_key = (y, mo)

            if day_key != cur_day:
                if cur_day is not None:
                    val, vah, poc = value_area(day_hist, day_vol, tick_size)
                    daily_rows.append((f"{cur_day[0]:04d}-{cur_day[1]:02d}-{cur_day[2]:02d}", val, vah, poc, dict(day_hist)))
                cur_day = day_key
                intraday = RunningVWAP()
                cum_delta = 0.0
                session_open = o
                day_hist = defaultdict(float)
                day_vol = 0.0

            if week_key != cur_week:
                cur_week = week_key
                weekly = RunningVWAP()

            if month_key != cur_month:
                cur_month = month_key
                monthly = RunningVWAP()

            intraday.add(typical, vol)
            weekly.add(typical, vol)
            monthly.add(typical, vol)
            cum_delta += askvol - bidvol

            bucket = round(last / tick_size) * tick_size
            day_hist[bucket] += vol
            day_vol += vol

            ts = f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}"
            writer.writerow([
                ts, instrument, last, session_open,
                monthly.vwap(), weekly.vwap(), intraday.vwap(), cum_delta,
                intraday.sd1_distance(), monthly.sd1_distance(), weekly.sd1_distance(),
            ])
            n += 1
            if n % 1_000_000 == 0:
                print(f"  ...{n:,} rows", file=sys.stderr)

        if cur_day is not None:
            val, vah, poc = value_area(day_hist, day_vol, tick_size)
            daily_rows.append((f"{cur_day[0]:04d}-{cur_day[1]:02d}-{cur_day[2]:02d}", val, vah, poc, dict(day_hist)))

    with open(f"{out_dir}/daily_profile_export.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "instrument", "val", "vah", "poc", "volume_at_price"])
        for date_s, val, vah, poc, hist in daily_rows:
            vap = ";".join(f"{price}:{vol}" for price, vol in hist.items())
            writer.writerow([date_s, instrument, val, vah, poc, vap])

    print(f"Done: {n:,} intraday rows, {len(daily_rows):,} daily profile rows.", file=sys.stderr)


if __name__ == "__main__":
    main()
