"""Načítání OHLC dat a generování syntetických dat pro testy."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

_TS_CANDIDATES = ("datetime", "timestamp", "time", "date", "gmt time", "local time")


def load_csv(path: str, tz: str = "UTC", sep: Optional[str] = None) -> pd.DataFrame:
    """Načte OHLC(V) CSV z běžných zdrojů (TradingView, MT4/MT5, Dukascopy...).

    Podporuje buď jeden sloupec s datem a časem, nebo oddělené sloupce
    `date` + `time`. `tz` je časová zóna, ve které jsou časy v souboru.
    Výsledek má tz-aware DatetimeIndex a sloupce open/high/low/close[/volume].
    """
    df = pd.read_csv(path, sep=sep, engine="python")
    df.columns = [str(c).strip().strip("<>").lower() for c in df.columns]

    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
    else:
        col = next((c for c in _TS_CANDIDATES if c in df.columns), df.columns[0])
        raw = df[col]
        if np.issubdtype(raw.dtype, np.number):  # unix timestamp
            unit = "ms" if raw.iloc[0] > 1e11 else "s"
            ts = pd.to_datetime(raw, unit=unit, utc=True)
        else:
            ts = pd.to_datetime(raw, utc=False, format="mixed", dayfirst=False)

    rename = {"vol": "volume", "tickvol": "volume", "tick_volume": "volume"}
    df = df.rename(columns=rename)
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"CSV neobsahuje sloupce: {sorted(missing)}")

    idx = pd.DatetimeIndex(ts)
    idx = idx.tz_localize(tz) if idx.tz is None else idx.tz_convert(tz)
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[cols].astype(float)
    out.index = idx
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
    x = np.linspace(-1, 1, n_bars)
    profile = 0.6 + 1.6 * x**2  # U-shape
    profile = profile / np.sqrt((profile**2).mean())
    bar_sigma = daily_vol / np.sqrt(n_bars) * profile
    orb_bars = orb_minutes // bar_minutes

    dates = pd.bdate_range("2020-01-02", periods=days)
    frames = []
    price = start_price
    for d in dates:
        vol_regime = np.exp(rng.normal(0, 0.35))
        gap = rng.normal(0, daily_vol * 0.3)
        price *= np.exp(gap)
        rets = rng.standard_t(5, n_bars) / np.sqrt(5 / 3) * bar_sigma * vol_regime
        if orb_drift:
            first = rets[:orb_bars].sum()
            rets[orb_bars:] += np.sign(first) * orb_drift * bar_sigma[orb_bars:] * vol_regime
        closes = price * np.exp(np.cumsum(rets))
        opens = np.concatenate([[price], closes[:-1]])
        wick = np.abs(rng.normal(0, 0.5, (2, n_bars))) * bar_sigma * vol_regime * closes
        highs = np.maximum(opens, closes) + wick[0]
        lows = np.minimum(opens, closes) - wick[1]
        idx = pd.date_range(
            pd.Timestamp.combine(d.date(), start.time()), periods=n_bars, freq=f"{bar_minutes}min"
        ).tz_localize(tz)
        frames.append(
            pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)
        )
        price = closes[-1]
    return pd.concat(frames)
