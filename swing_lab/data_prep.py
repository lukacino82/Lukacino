"""
ES data preparation for the Multi-Swing System lab.

Sources (in repo root, split zips):
  * ES3000.zip/.z01/.z02            -> ES3000.txt, 1-minute ES bars 2018-07-08 .. 2026-09-23,
                                       UNADJUSTED front contract (roll gaps every quarter), ET time,
                                       with BidVolume/AskVolume (-> delta).
  * es mini data new 2 (2).zip/...  -> xlsx, sheet List1: volume bars (5000 contracts) 2016-07-19 .. 2026-07-17,
                                       BACK-ADJUSTED continuous contract, ET time, with Bid/Ask volume.

Output (swing_lab/data/, git-ignored):
  * es1m_adj.parquet  continuous back-adjusted intraday bars 2016-07-19 .. 2026-09-23
                      (Excel volume bars before 2018-07-09, ES3000 1-min bars after)
  * rolls.csv         roll dates and the roll premium used for adjustment

Roll handling
  ES3000 rolls on the Sunday evening of expiry week (3rd Friday - 5 days). The Excel series is
  continuous, so the step change of (Excel - ES3000) across each roll weekend equals the roll
  premium exactly (weekend market moves cancel). For the Sep-2026 roll (after Excel ends) the
  premium is estimated as the mean of the previous 4 rolls.
  Back-adjustment is ADDITIVE (points), anchored to the latest contract -> P&L in points is exact
  per 1 contract and prices at the end equal real traded prices.
"""
from __future__ import annotations

import datetime as dt
import io
import struct
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"


def _extract_split_zip(parts: list[Path]) -> bytes:
    """Split zips uploaded through GitHub web are concatenated raw; inflate the single member."""
    blob = b"".join(p.read_bytes() for p in parts)
    i = blob.find(b"PK\x03\x04")
    fnl, exl = struct.unpack("<HH", blob[i + 26:i + 30])
    start = i + 30 + fnl + exl
    d = zlib.decompressobj(-15)
    out = io.BytesIO()
    pos = start
    while not d.eof and pos < len(blob):
        out.write(d.decompress(blob[pos:pos + (8 << 20)]))
        pos += 8 << 20
    if not d.eof:
        raise RuntimeError("archive truncated")
    return out.getvalue()


def load_es3000() -> pd.DataFrame:
    cache = DATA / "es3000_raw.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    raw = _extract_split_zip([ROOT / "ES3000.z01", ROOT / "ES3000.z02", ROOT / "ES3000.zip"])
    df = pd.read_csv(io.BytesIO(raw), skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df["dt"] = pd.to_datetime(df["Date"] + " " + df["Time"], format="%Y/%m/%d %H:%M:%S")
    df = df.drop(columns=["Date", "Time"]).set_index("dt")
    df.to_parquet(cache)
    return df


def load_excel_bars() -> pd.DataFrame:
    cache = DATA / "excel_raw.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    import openpyxl

    base = "es mini data new 2 (2)"
    raw = _extract_split_zip([ROOT / f"{base}.z01", ROOT / f"{base}.z02", ROOT / f"{base}.zip"])
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
    rows = []
    for i, r in enumerate(wb["List1"].iter_rows(values_only=True)):
        if i == 0 or r[0] is None:
            continue
        rows.append(r[:10])
    cols = ["Date", "Time", "Open", "High", "Low", "Last", "Volume", "NumberOfTrades", "BidVolume", "AskVolume"]
    x = pd.DataFrame(rows, columns=cols)
    x["dt"] = [dt.datetime.combine(d.date(), t) for d, t in zip(x.Date, x.Time)]
    x = x.drop(columns=["Date", "Time"]).set_index("dt")
    x.to_parquet(cache)
    return x


def _third_friday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 15)
    while d.weekday() != 4:
        d += dt.timedelta(1)
    return d


def estimate_rolls(es: pd.DataFrame, xl: pd.DataFrame) -> pd.DataFrame:
    xm = xl["Last"].copy()
    xm.index = xm.index.floor("min")
    xm = xm.groupby(level=0).last()
    j = pd.concat([es["Last"], xm], axis=1, keys=["es", "xl"], sort=True).dropna()
    diff = (j.xl - j.es).groupby(j.index.date).median()
    diff.index = pd.to_datetime(diff.index)
    rows = []
    for y in range(2018, 2027):
        for m in (3, 6, 9, 12):
            sun = pd.Timestamp(_third_friday(y, m) - dt.timedelta(5))
            if sun < es.index[0] or sun > es.index[-1]:
                continue
            before = diff[(diff.index < sun) & (diff.index >= sun - pd.Timedelta(days=4))]
            after = diff[(diff.index >= sun) & (diff.index <= sun + pd.Timedelta(days=2))]
            prem = np.nan
            if len(before) and len(after):
                prem = -(after.mean() - before.iloc[-1])
            rows.append({"roll_time": sun + pd.Timedelta(hours=18), "premium": prem, "source": "excel_step"})
    r = pd.DataFrame(rows)
    miss = r.premium.isna()
    for i in r.index[miss]:
        r.loc[i, "premium"] = r.premium.iloc[max(0, i - 4):i].mean()
        r.loc[i, "source"] = "estimate_mean_last4"
    r["premium"] = (r.premium * 4).round() / 4  # tick grid
    return r


def build(force: bool = False) -> pd.DataFrame:
    DATA.mkdir(exist_ok=True)
    out = DATA / "es1m_adj.parquet"
    if out.exists() and not force:
        return pd.read_parquet(out)
    es = load_es3000()
    xl = load_excel_bars()
    xl = xl[~xl.index.duplicated(keep="first")]
    rolls = estimate_rolls(es, xl)
    rolls.to_csv(DATA / "rolls.csv", index=False)

    # additive back adjustment: bars before roll r get + premium_r
    adj = np.zeros(len(es))
    t = es.index.values
    for _, r in rolls.iterrows():
        adj[t < np.datetime64(r.roll_time)] += r.premium
    es_adj = es.copy()
    for c in ["Open", "High", "Low", "Last"]:
        es_adj[c] = es_adj[c] + adj

    # Excel before ES3000 start, shifted onto ES-adjusted reference (median offset of first 5 overlap days)
    start = es.index[0]
    xm = xl["Last"].copy()
    xm.index = xm.index.floor("min")
    xm = xm.groupby(level=0).last()
    ov = pd.concat([es_adj["Last"], xm], axis=1, keys=["es", "xl"], sort=True).dropna()
    ov = ov[ov.index < start + pd.Timedelta(days=7)]
    off = float(np.round((ov.xl - ov.es).median() * 4) / 4)
    pre = xl[xl.index < start].copy()
    for c in ["Open", "High", "Low", "Last"]:
        pre[c] = pre[c] - off
    pre["src"] = 0
    es_adj["src"] = 1
    full = pd.concat([pre, es_adj]).sort_index()
    full = full.rename(columns={"Last": "Close"})
    full["Delta"] = full["AskVolume"] - full["BidVolume"]
    full = full[["Open", "High", "Low", "Close", "Volume", "BidVolume", "AskVolume", "Delta", "src"]]
    full.to_parquet(out)
    print(f"excel->es offset {off}; rolls:\n{rolls}")
    return full


if __name__ == "__main__":
    build(force=True)
