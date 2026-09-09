"""Plain CSV/text file contract between the Python engine and the ACSIL study.

See ARCHITECTURE.md ("ACSIL <-> Python bridge") for why this is plain text
rather than JSON. Every format detail (column order, empty-value rules) is
defined here in one place; both this module's writer and reader must agree
with the ACSIL side's parsing.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from ..composite.models import Composite, DailyProfile, classify_tier


@dataclass(frozen=True)
class LiveMarketState:
    """A single real-time snapshot ACSIL writes on its refresh interval.

    Unlike ``DailyProfile`` (one row per closed session), this is
    overwritten in place every refresh — it's the current VWAP tiers and
    cumulative delta for a still-open trading day, not a history.
    """

    instrument: str
    timestamp: datetime
    last_price: float
    vwap_monthly: float
    vwap_weekly: float
    vwap_intraday: float
    cum_delta: float

DAILY_PROFILE_FIELDS = ["date", "instrument", "val", "vah", "poc"]
LIVE_STATE_FIELDS = [
    "timestamp",
    "instrument",
    "last_price",
    "vwap_monthly",
    "vwap_weekly",
    "vwap_intraday",
    "cum_delta",
]
COMPOSITE_FIELDS = [
    "instrument",
    "start_date",
    "end_date",
    "val",
    "vah",
    "day_count",
    "tier",
    "active",
    "invalidated_on",
    "remaining_ranges",
]


def _format_ranges(ranges: Tuple[Tuple[float, float], ...]) -> str:
    return ";".join(f"{lo}:{hi}" for lo, hi in ranges)


def _parse_ranges(text: str) -> Tuple[Tuple[float, float], ...]:
    if not text:
        return ()
    segments = []
    for part in text.split(";"):
        lo_str, hi_str = part.split(":")
        segments.append((float(lo_str), float(hi_str)))
    return tuple(segments)


def write_daily_profiles(path: Path, profiles: Iterable[DailyProfile]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(DAILY_PROFILE_FIELDS)
        for p in profiles:
            writer.writerow([p.session_date.isoformat(), p.instrument, p.val, p.vah, p.poc])


def read_daily_profiles(path: Path) -> List[DailyProfile]:
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [
            DailyProfile(
                instrument=row["instrument"],
                session_date=date.fromisoformat(row["date"]),
                val=float(row["val"]),
                vah=float(row["vah"]),
                poc=float(row["poc"]),
            )
            for row in reader
        ]


def write_live_state(path: Path, state: LiveMarketState) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LIVE_STATE_FIELDS)
        writer.writerow(
            [
                state.timestamp.isoformat(),
                state.instrument,
                state.last_price,
                state.vwap_monthly,
                state.vwap_weekly,
                state.vwap_intraday,
                state.cum_delta,
            ]
        )


def read_live_state(path: Path) -> Optional[LiveMarketState]:
    """Returns ``None`` if ACSIL hasn't written a snapshot yet (empty/missing rows)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
    if row is None:
        return None
    return LiveMarketState(
        instrument=row["instrument"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        last_price=float(row["last_price"]),
        vwap_monthly=float(row["vwap_monthly"]),
        vwap_weekly=float(row["vwap_weekly"]),
        vwap_intraday=float(row["vwap_intraday"]),
        cum_delta=float(row["cum_delta"]),
    )


def write_composites(path: Path, composites: Iterable[Composite]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COMPOSITE_FIELDS)
        for c in composites:
            writer.writerow(
                [
                    c.instrument,
                    c.start_date.isoformat(),
                    c.end_date.isoformat(),
                    c.val,
                    c.vah,
                    c.day_count,
                    c.tier.value,
                    "1" if c.is_active else "0",
                    c.invalidated_on.isoformat() if c.invalidated_on else "",
                    _format_ranges(c.remaining_ranges),
                ]
            )


def read_composites(path: Path) -> List[Composite]:
    result = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            day_count = int(row["day_count"])
            tier = classify_tier(day_count)
            if tier.value != row["tier"]:
                raise ValueError(
                    f"composites.csv row for {row['instrument']} has tier "
                    f"{row['tier']!r} but day_count {day_count} implies {tier.value!r}"
                )
            composite = Composite(
                instrument=row["instrument"],
                start_date=date.fromisoformat(row["start_date"]),
                end_date=date.fromisoformat(row["end_date"]),
                val=float(row["val"]),
                vah=float(row["vah"]),
                day_count=day_count,
            )
            if row["active"] == "0":
                composite.invalidate(
                    by_id="",
                    on=date.fromisoformat(row["invalidated_on"]),
                    remaining_ranges=_parse_ranges(row["remaining_ranges"]),
                )
            result.append(composite)
    return result


def write_hypothesis(path: Path, instrument: str, generated_at: datetime, body: str) -> None:
    with open(path, "w") as f:
        f.write(f"{instrument}|{generated_at.isoformat()}\n")
        f.write(body)


def read_hypothesis(path: Path) -> Tuple[str, datetime, str]:
    with open(path) as f:
        header = f.readline().rstrip("\n")
        body = f.read()
    instrument, generated_at_str = header.split("|", 1)
    return instrument, datetime.fromisoformat(generated_at_str), body
