"""Empirický profil volatility podle času dne a dne v týdnu.

Místo odhadu „kdy je trh nejživější“ to změříme: průměrný range baru
v každém časovém okně, normalizovaný průměrem dne. Okna s poměrem výrazně
nad 1.0 jsou kandidáti pro range/průraz logiky.
"""
from __future__ import annotations

import pandas as pd


def volatility_profile(data: pd.DataFrame, tz: str, bucket: str = "30min") -> pd.DataFrame:
    df = data.tz_convert(tz)
    rng = (df["high"] - df["low"]) / df["close"]
    ret = df["close"].pct_change().abs()
    # normalizace denním průměrem odstraní vliv klidných/divokých režimů
    day_mean = rng.groupby(df.index.date).transform("mean")
    b = df.index.floor(bucket).time
    prof = pd.DataFrame({"rel_range": rng / day_mean, "abs_ret_bp": ret * 1e4, "bucket": b})
    out = prof.groupby("bucket").agg(
        rel_range=("rel_range", "mean"),
        abs_ret_bp=("abs_ret_bp", "mean"),
        bars=("rel_range", "size"),
    )
    out["rank"] = out["rel_range"].rank(ascending=False).astype(int)
    return out


def weekday_profile(data: pd.DataFrame, tz: str) -> pd.DataFrame:
    df = data.tz_convert(tz)
    daily = df.groupby(df.index.date).agg(high=("high", "max"), low=("low", "min"),
                                          close=("close", "last"))
    daily.index = pd.to_datetime(daily.index)
    daily["range_pct"] = (daily["high"] - daily["low"]) / daily["close"] * 100
    names = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
    g = daily.groupby(daily.index.dayofweek)["range_pct"].mean()
    g.index = [names[i] for i in g.index]
    return g.to_frame("avg_range_pct")
