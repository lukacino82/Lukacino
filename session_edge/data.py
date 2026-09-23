"""Načítání OHLC dat a generování syntetických dat pro testy."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

_TS_CANDIDATES = ("datetime", "timestamp", "time", "date", "gmt time", "local time")


def _parse_stamp(stamp: pd.Series) -> pd.Series:
    """Rychlé parsování běžných formátů, jinak obecný (pomalý) parser."""
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y%m%d %H%M%S",
                "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return pd.to_datetime(stamp, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(stamp, format="mixed")


def _sniff(path: str) -> tuple[str, bool]:
    """Zjistí oddělovač a zda má soubor hlavičku."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
    sep = next((c for c in (";", "\t", ",") if c in first), r"\s+")
    has_header = any(ch.isalpha() for ch in first.replace("T", "").replace("Z", ""))
    return sep, has_header


def load_csv(
    path: str,
    tz: str = "UTC",
    sep: Optional[str] = None,
    bar_time: str = "open",
) -> pd.DataFrame:
    """Načte OHLC(V) data z běžných zdrojů.

    Podporované formáty:
    * s hlavičkou: TradingView, MT4/MT5 (`<DATE> <TIME> ...`), Dukascopy, unix ts
    * bez hlavičky: NinjaTrader export `20240102 093100;o;h;l;c;v`,
      nebo `datum,čas,o,h,l,c[,v]` / `datum čas,o,h,l,c[,v]`

    `tz` = časová zóna časů v souboru. `bar_time="close"` znamená, že čas
    v souboru označuje konec baru (NinjaTrader, TradeStation) – převede se
    na čas otevření, který používá engine.
    """
    sniff_sep, has_header = _sniff(path)
    sep = sep or sniff_sep
    if has_header:
        df = pd.read_csv(path, sep=sep, engine="python")
        df.columns = [str(c).strip().strip("<>").lower() for c in df.columns]
        if "date" in df.columns and "time" in df.columns:
            stamp = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
            ts = _parse_stamp(stamp)
        else:
            col = next((c for c in _TS_CANDIDATES if c in df.columns), df.columns[0])
            raw = df[col]
            if np.issubdtype(raw.dtype, np.number):  # unix timestamp
                unit = "ms" if raw.iloc[0] > 1e11 else "s"
                ts = pd.to_datetime(raw, unit=unit, utc=True)
            else:
                ts = pd.to_datetime(raw, utc=False, format="mixed", dayfirst=False)
    else:
        df = pd.read_csv(path, sep=sep, header=None, engine="c" if len(sep) == 1 else "python",
                         dtype=str)
        first = df.iloc[0, 0].strip()
        n_num = df.shape[1]
        if " " in first:  # "20240102 093100" nebo "2024-01-02 09:31:00"
            stamp, rest = df[0].str.strip(), 1
        else:  # datum a čas ve dvou sloupcích
            stamp, rest = df[0].str.strip() + " " + df[1].str.strip(), 2
        fmt = "%Y%m%d %H%M%S" if first.replace(" ", "").isdigit() and len(first) == 15 else "mixed"
        ts = pd.to_datetime(stamp, format=fmt)
        names = ["open", "high", "low", "close", "volume"][: n_num - rest]
        df = df.iloc[:, rest: rest + len(names)]
        df.columns = names

    rename = {"vol": "volume", "tickvol": "volume", "tick_volume": "volume", "last": "close"}
    df = df.rename(columns=rename)
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"CSV neobsahuje sloupce: {sorted(missing)}")

    idx = pd.DatetimeIndex(ts)
    if bar_time == "close":
        step = pd.Series(idx).diff().dropna()
        idx = idx - step[step > pd.Timedelta(0)].mode().iloc[0]
    if idx.tz is None:
        idx = idx.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
    else:
        idx = idx.tz_convert(tz)
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[cols].astype(float)
    out.index = idx
    out = out[out.index.notna()]
    out = out[~out.index.duplicated(keep="first")].sort_index()
    return validate_ohlc(out)


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise ValueError("Data musí mít DatetimeIndex s časovou zónou")
    bad = (df["high"] < df[["open", "close"]].max(axis=1)) | (
        df["low"] > df[["open", "close"]].min(axis=1)
    )
    if bad.any():
        # opravíme drobné nekonzistence z dat brokerů místo tichého pádu
        df = df.copy()
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"] = df[["open", "low", "close"]].min(axis=1)
    return df.dropna(subset=["open", "high", "low", "close"])


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    return df.resample(rule, label="left", closed="left").agg(agg).dropna()


def synthetic_intraday(
    days: int = 500,
    bar_minutes: int = 5,
    tz: str = "America/New_York",
    session: tuple[str, str] = ("09:30", "16:00"),
    daily_vol: float = 0.012,
    start_price: float = 4000.0,
    orb_drift: float = 0.0,
    orb_minutes: int = 30,
    seed: int = 0,
) -> pd.DataFrame:
    """Syntetické intradenní ceny s U-profilem volatility (vysoká na otevření
    a zavření, nízká přes poledne) – tak jak to vypadá na reálných trzích.

    `orb_drift` > 0 vloží do dat umělou hranu: po opening range pokračuje cena
    ve směru prvních `orb_minutes` minut. Slouží k ověření, že validační
    testy hranu najdou; `orb_drift = 0` je náhodná procházka bez hrany.
    """
    rng = np.random.default_rng(seed)
    start = pd.Timestamp(session[0])
    end = pd.Timestamp(session[1])
    n_bars = int((end - start) / pd.Timedelta(minutes=bar_minutes))
    sub = 60  # high/low baru se počítá z jemné cesty, ne z náhodných knotů
    x = np.linspace(-1, 1, n_bars)
    profile = 0.6 + 1.6 * x**2  # U-shape
    profile = profile / np.sqrt((profile**2).mean())
    bar_sigma = daily_vol / np.sqrt(n_bars) * profile
    step_sigma = np.repeat(bar_sigma / np.sqrt(sub), sub)
    orb_steps = orb_minutes // bar_minutes * sub

    dates = pd.bdate_range("2020-01-02", periods=days)
    frames = []
    price = start_price
    for d in dates:
        vol_regime = np.exp(rng.normal(0, 0.35))
        price *= np.exp(rng.normal(0, daily_vol * 0.3))  # overnight gap
        rets = rng.standard_t(5, n_bars * sub) / np.sqrt(5 / 3) * step_sigma * vol_regime
        if orb_drift:
            first = rets[:orb_steps].sum()
            rets[orb_steps:] += np.sign(first) * orb_drift * step_sigma[orb_steps:] / np.sqrt(sub) * vol_regime
        path = (price * np.exp(np.cumsum(rets))).reshape(n_bars, sub)
        closes = path[:, -1]
        opens = np.concatenate([[price], closes[:-1]])
        highs = np.maximum(path.max(axis=1), opens)
        lows = np.minimum(path.min(axis=1), opens)
        idx = pd.date_range(
            pd.Timestamp.combine(d.date(), start.time()), periods=n_bars, freq=f"{bar_minutes}min"
        ).tz_localize(tz)
        frames.append(
            pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)
        )
        price = closes[-1]
    return pd.concat(frames)
