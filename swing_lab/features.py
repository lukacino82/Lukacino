"""
Daily feature matrix for swing research.

Every trading day d is split into two segments:
  ON  (overnight) = everything after RTH close of d-1 up to 09:30 of d   (Globex 16:00-17:00, 18:00-09:30)
  RTH             = 09:30 - 16:00 of d
A swing position is exposed to both, so stops/targets are checked in both segments.

All features in row d are known at the RTH close of d (no look-ahead). Signals built on them may
execute at the close of d (MOC-style), at the next RTH open, or with a resting limit/stop order
during day d+1.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_prep import DATA, build


# ---------------------------------------------------------------- helpers
def sma(x, n):
    return x.rolling(n, min_periods=n).mean()


def ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close, n):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(up.notna())


def streak(cond: pd.Series) -> pd.Series:
    """length of the current run of True values"""
    c = cond.astype(int)
    grp = (c != c.shift()).cumsum()
    return c.groupby(grp).cumsum() * c


def adx(h, l, c, n=14):
    up = h.diff()
    dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    ndi = 100 * pd.Series(ndm, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, ndi


def value_area(prices: np.ndarray, vols: np.ndarray, pct=0.70):
    """POC / VAH / VAL from a volume-at-price histogram (1 point bins)."""
    if len(prices) == 0 or vols.sum() <= 0:
        return np.nan, np.nan, np.nan
    b = np.round(prices).astype(np.int64)
    lo = b.min()
    hist = np.bincount(b - lo, weights=vols)
    poc = int(hist.argmax())
    tot = hist.sum()
    i = j = poc
    acc = hist[poc]
    while acc < pct * tot and (i > 0 or j < len(hist) - 1):
        up = hist[j + 1] if j < len(hist) - 1 else -1
        dn = hist[i - 1] if i > 0 else -1
        if up >= dn:
            j += 1
            acc += hist[j]
        else:
            i -= 1
            acc += hist[i]
    return lo + poc, lo + j, lo + i


# ---------------------------------------------------------------- main build
def build_daily(force: bool = False):
    out = DATA / "daily.parquet"
    out30 = DATA / "bars30.npz"
    if out.exists() and out30.exists() and not force:
        return pd.read_parquet(out), dict(np.load(out30))

    m = build()
    t = m.index
    tod = t.hour * 60 + t.minute
    is_rth = (tod >= 570) & (tod < 960)
    rth = m[is_rth]
    rth_day = pd.DatetimeIndex(rth.index.normalize())
    days = pd.DatetimeIndex(np.unique(rth_day.values))
    # drop truncated RTH days (partial data at dataset edges) but keep half-days (>=150 min)
    cnt = pd.Series(1, index=rth_day).groupby(level=0).size()
    days = days[cnt.reindex(days).values >= 20]

    # segment day for every bar: RTH -> its date; non-RTH -> next RTH day
    day_open = days + pd.Timedelta(minutes=570)
    seg_day_idx = np.searchsorted(day_open.values, t.values, side="right") - 1  # RTH bars: own day
    nonrth_idx = np.searchsorted(day_open.values, t.values, side="left")        # ON bars: next day
    seg_idx = np.where(is_rth, seg_day_idx, nonrth_idx)
    # RTH bars on days that were dropped fall into -1/garbage -> mark invalid
    valid = (seg_idx >= 0) & (seg_idx < len(days))
    rth_ok = is_rth & valid
    rth_ok[rth_ok] = days.values[seg_idx[rth_ok]] == t.values[rth_ok].astype("datetime64[D]")
    seg = np.where(is_rth, 1, 0)
    keep = valid & (~is_rth | rth_ok)
    m = m[keep].copy()
    m["di"] = seg_idx[keep]
    m["seg"] = seg[keep]

    g = m.groupby(["di", "seg"])
    agg = g.agg(o=("Open", "first"), h=("High", "max"), l=("Low", "min"), c=("Close", "last"),
                v=("Volume", "sum"), dl=("Delta", "sum"))
    rt = agg.xs(1, level="seg").reindex(range(len(days)))
    on = agg.xs(0, level="seg").reindex(range(len(days)))

    d = pd.DataFrame(index=days)
    d["open"] = rt.o.values
    d["high"] = rt.h.values
    d["low"] = rt.l.values
    d["close"] = rt.c.values
    d["volume"] = rt.v.values
    d["delta"] = rt.dl.values
    d["on_open"] = on.o.values
    d["on_high"] = on.h.values
    d["on_low"] = on.l.values
    d["on_delta"] = on.dl.values
    d["on_volume"] = on.v.values
    # when there is no overnight data, the ON segment is flat at the previous close
    pc = d.close.shift()
    for c_ in ["on_open", "on_high", "on_low"]:
        d[c_] = d[c_].fillna(d.open)
    d["eth_high"] = np.fmax(d.high, d.on_high)
    d["eth_low"] = np.fmin(d.low, d.on_low)
    d["eth_delta"] = d.delta + d.on_delta.fillna(0)
    d["cumdelta"] = d.eth_delta.cumsum()

    # ---------------- VWAPs (ETH, anchored to calendar period of the trading day) ----------------
    tp = (m.High + m.Low + m.Close) / 3
    vol = m.Volume.astype(float)
    di = m.di.values
    dayidx = days[di]
    m["tpv"] = tp * vol
    m["tp2v"] = tp * tp * vol

    def anchored(key):
        k = pd.Series(key, index=m.index)
        cv = vol.groupby(k).cumsum()
        ctpv = m.tpv.groupby(k).cumsum()
        ctp2v = m.tp2v.groupby(k).cumsum()
        vw = ctpv / cv
        sd = np.sqrt(np.maximum(ctp2v / cv - vw * vw, 0))
        # value at RTH close of each day = last bar of RTH seg of that day
        last = pd.DataFrame({"vw": vw.values, "sd": sd.values, "di": di, "seg": m.seg.values})
        last = last[last.seg == 1].groupby("di").last()
        return last.vw.reindex(range(len(days))).values, last.sd.reindex(range(len(days))).values

    periods = {
        "dvwap": di,  # session VWAP (ETH day)
        "wvwap": (dayidx.to_period("W-SUN").astype("int64")).values if False else dayidx.to_period("W").asi8,
        "mvwap": dayidx.to_period("M").asi8,
        "qvwap": dayidx.to_period("Q").asi8,
        "yvwap": dayidx.to_period("Y").asi8,
    }
    # RTH-only session VWAP too
    for name, key in periods.items():
        vw, sd = anchored(key)
        d[name] = vw
        d[name + "_sd"] = sd
    # RTH VWAP
    r = m[m.seg == 1]
    rv = (r.tpv.groupby(r.di).sum() / r.Volume.groupby(r.di).sum()).reindex(range(len(days))).values
    d["rvwap"] = rv

    # previous completed period VWAP (final value) - classic reference levels
    for name, per in [("wvwap", "W"), ("mvwap", "M"), ("qvwap", "Q")]:
        p = d.index.to_period(per)
        last_val = d[name].groupby(p).last()
        d["prev_" + name] = p.map(last_val.shift()).values

    # ---------------- volume profile: prior day and prior week ----------------
    px = m.Close.values
    vv = vol.values
    order = np.argsort(di, kind="stable")
    bounds = np.searchsorted(di[order], np.arange(len(days) + 1))
    poc = np.full(len(days), np.nan)
    vah = poc.copy()
    val = poc.copy()
    for k in range(len(days)):
        sl = order[bounds[k]:bounds[k + 1]]
        sl = sl[m.seg.values[sl] == 1]
        poc[k], vah[k], val[k] = value_area(px[sl], vv[sl])
    d["poc"], d["vah"], d["val"] = poc, vah, val
    wk = days.to_period("W").asi8
    wpoc = np.full(len(days), np.nan)
    wvah = wpoc.copy()
    wval = wpoc.copy()
    wkm = wk[di]
    for w in np.unique(wk):
        sel = wkm == w
        p_, h_, l_ = value_area(px[sel], vv[sel])
        idx = np.where(wk == w)[0]
        wpoc[idx], wvah[idx], wval[idx] = p_, h_, l_
    # prior-week profile (completed) for each day
    wdf = pd.DataFrame({"wk": wk, "poc": wpoc, "vah": wvah, "val": wval}).groupby("wk").first()
    prevw = wdf.shift()
    d["pw_poc"] = prevw.poc.reindex(wk).values
    d["pw_vah"] = prevw.vah.reindex(wk).values
    d["pw_val"] = prevw.val.reindex(wk).values

    # ---------------- 30-min bars for intraday path resolution ----------------
    b = m.copy()
    b["bucket"] = b.index.floor("30min")
    bb = b.groupby(["di", "seg", "bucket"]).agg(o=("Open", "first"), h=("High", "max"),
                                                 l=("Low", "min"), c=("Close", "last")).reset_index()
    bb = bb.sort_values(["di", "seg", "bucket"])
    key = bb.di.values * 2 + bb.seg.values
    start = np.searchsorted(key, np.arange(len(days) * 2))
    end = np.searchsorted(key, np.arange(len(days) * 2), side="right")
    bars30 = {"o": bb.o.values, "h": bb.h.values, "l": bb.l.values, "c": bb.c.values,
              "start": start, "end": end}
    np.savez(out30, **bars30)

    d = add_indicators(d)
    d.to_parquet(out)
    return d, bars30


def add_indicators(d: pd.DataFrame) -> pd.DataFrame:
    c, h, l, o = d.close, d.high, d.low, d.open
    pc = c.shift()
    d["ret"] = c.diff()
    d["gap"] = o - pc
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    etr = pd.concat([d.eth_high - d.eth_low, (d.eth_high - pc).abs(), (d.eth_low - pc).abs()], axis=1).max(axis=1)
    d["tr"] = tr
    for n in (5, 10, 14, 20, 50):
        d[f"atr{n}"] = etr.rolling(n).mean()
    for n in (3, 5, 10, 20, 50, 100, 200):
        d[f"sma{n}"] = sma(c, n)
    for n in (8, 21, 50):
        d[f"ema{n}"] = ema(c, n)
    for n in (2, 3, 4, 5, 14):
        d[f"rsi{n}"] = rsi(c, n)
    d["crsi2_2"] = d.rsi2 + d.rsi2.shift()          # Connors cumulative RSI(2) over 2 days
    d["crsi2_3"] = d.crsi2_2 + d.rsi2.shift(2)
    # Connors RSI: (RSI3 + RSI2(streak) + PercentRank(ROC1,100))/3
    upst = streak(c > pc)
    dnst = streak(c < pc)
    st = upst - dnst
    d["updays"], d["downdays"] = upst, dnst
    d["connors_rsi"] = (d.rsi3 + rsi(st.astype(float), 2) + (c.pct_change().rolling(100).rank(pct=True) * 100)) / 3
    d["ibs"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5)
    d["lower_lows"] = streak(l < l.shift())
    d["higher_highs"] = streak(h > h.shift())
    for n in (5, 7, 10, 20, 50):
        d[f"ll{n}"] = c <= c.rolling(n).min()      # close at n-day low close
        d[f"hh{n}"] = c >= c.rolling(n).max()
        d[f"lowN{n}"] = l.rolling(n).min()
        d[f"highN{n}"] = h.rolling(n).max()
    bbm, bbs = sma(c, 20), c.rolling(20).std()
    d["bb_pctb"] = (c - (bbm - 2 * bbs)) / (4 * bbs)
    d["wr10"] = -100 * (d.highN10 - c) / (d.highN10 - d.lowN10)
    d["adx14"], d["pdi"], d["ndi"] = adx(h, l, c, 14)
    ath = h.cummax()
    d["dd_ath"] = c / ath - 1
    d["ath_prev"] = ath.shift()
    d["ret5"], d["ret10"], d["ret20"] = c - c.shift(5), c - c.shift(10), c - c.shift(20)
    d["dist200_atr"] = (c - d.sma200) / d.atr20
    d["delta_z"] = (d.eth_delta - d.eth_delta.rolling(50).mean()) / d.eth_delta.rolling(50).std()
    d["vol_z"] = (d.volume - d.volume.rolling(50).mean()) / d.volume.rolling(50).std()
    for n in (3, 5, 10):
        d[f"cd{n}"] = d.cumdelta - d.cumdelta.shift(n)   # net aggressive flow over n days
    # calendar
    idx = d.index
    d["dow"] = idx.dayofweek
    mon = idx.to_period("M")
    d["tdm"] = pd.Series(1, index=idx).groupby(mon).cumsum().values            # trading day of month 1..
    d["tdm_rev"] = pd.Series(1, index=idx)[::-1].groupby(mon[::-1]).cumsum()[::-1].values  # 1 = last day
    nxt = pd.Series(idx, index=idx).shift(-1)
    bd_gap = np.busday_count(idx.values.astype("datetime64[D]"),
                             nxt.fillna(idx[-1] + pd.Timedelta(days=1)).values.astype("datetime64[D]"))
    d["pre_holiday"] = bd_gap > 1
    third_fri = [(p.start_time + pd.offsets.WeekOfMonth(week=2, weekday=4)) for p in mon]
    d["opex_week"] = [abs((x - tf).days) <= 4 and x <= tf for x, tf in zip(idx, third_fri)]
    d["year"] = idx.year
    return d


if __name__ == "__main__":
    import time

    t0 = time.time()
    dd, b30 = build_daily(force=True)
    print(dd.shape, time.time() - t0)
    print(dd[["open", "high", "low", "close", "dvwap", "wvwap", "mvwap", "poc", "vah", "val", "cumdelta"]].tail())
