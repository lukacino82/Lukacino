"""Plain CSV/text file contract between the Python engine and the ACSIL study.

See ARCHITECTURE.md ("ACSIL <-> Python bridge") for why this is plain text
rather than JSON. Every format detail (column order, empty-value rules) is
defined here in one place; both this module's writer and reader must agree
with the ACSIL side's parsing.
"""

from __future__ import annotations

import csv
from collections import OrderedDict
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
    session_open: float
    vwap_monthly: float
    vwap_weekly: float
    vwap_intraday: float
    cum_delta: float
    # Distance from vwap_intraday to its +1 standard deviation band (ACSIL
    # computes this from the intraday VWAP study's own SD band subgraph,
    # not recomputed here) -- 0.0 (the default) means "not available", the
    # same convention InstrumentConfig.fixed_risk_points/usd already use
    # for "not configured". See hypothesis/generator.py's module docstring
    # and run_live.py's resolve_fixed_risk_distance for how this feeds a
    # live, per-tick alternative to a flat fixed_risk_points/usd number --
    # added at the user's request to use "1 SD VWAP envelope" as the stop
    # distance instead of a static one.
    vwap_intraday_sd1: float = 0.0
    # Same mechanism, one band each for the monthly/weekly VWAP studies --
    # needed to read "MM bullish but cooling" (price retreated from outside
    # 2SD to inside 1SD, still above the VWAP line) as a number instead of
    # just the bare above/below Position tiers.py already gives. See
    # hypothesis/synthesis.py's classify_htf_bias for how this feeds the
    # multi-timeframe weighted synthesis model (ARCHITECTURE.md item 8).
    # 0.0 (the default) means "not available", same convention as
    # vwap_intraday_sd1 above.
    vwap_monthly_sd1: float = 0.0
    vwap_weekly_sd1: float = 0.0

@dataclass(frozen=True)
class OrderProposalSnapshot:
    """A single, always-present row describing what SEMI_AUTO's order
    proposal looks like right now.

    Unlike ``hypothesis.txt`` (free text meant for a human/chart display),
    this is the machine-readable counterpart ACSIL parses to actually place
    an order (Step 4's manual-trigger and, later, auto modes). Always
    written every tick, even when nothing is tradeable
    (``direction="none"``, ``contracts=0``) -- that way ACSIL can check
    both actionability (``contracts > 0``) and freshness (``timestamp``
    recent) from one row, without a separate "does a real proposal exist"
    file check that could race with a stale leftover file.
    """

    timestamp: datetime
    instrument: str
    direction: str  # "long", "short", or "none" when nothing is tradeable
    hypothesis_type: str  # HypothesisType.value (e.g. "A long"), "" when direction == "none"
    confluence: str  # Confluence.value, "" when direction == "none"
    entry: Optional[float]
    stop: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    runner: Optional[float]
    contracts: int
    # Scale-out split of `contracts` across target_1/target_2/runner,
    # decided by risk.order._split_contracts_by_confluence -- always sums to
    # `contracts`. 0/0/0 when direction == "none". ACSIL places one bracket
    # order per nonzero leg.
    contracts_target1: int
    contracts_target2: int
    contracts_runner: int


ORDER_PROPOSAL_FIELDS = [
    "timestamp",
    "instrument",
    "direction",
    "hypothesis_type",
    "confluence",
    "entry",
    "stop",
    "target_1",
    "target_2",
    "runner",
    "contracts",
    "contracts_target1",
    "contracts_target2",
    "contracts_runner",
]

DAILY_PROFILE_FIELDS = ["date", "instrument", "val", "vah", "poc"]
LIVE_STATE_FIELDS = [
    "timestamp",
    "instrument",
    "last_price",
    "session_open",
    "vwap_monthly",
    "vwap_weekly",
    "vwap_intraday",
    "cum_delta",
    "vwap_intraday_sd1",
    "vwap_monthly_sd1",
    "vwap_weekly_sd1",
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
    """Reads every row, keeping only the LAST one for each (instrument,
    date) pair when the file has more than one.

    ACSIL is expected to write exactly one row per closed trading day, but
    a real run surfaced duplicate/conflicting rows for the same date (two
    concurrent study instances briefly writing the same bridge file, one of
    them misconfigured, is the leading suspect -- see ARCHITECTURE.md).
    Silently keeping the FIRST row per date (a plain list comprehension's
    natural behavior) risks permanently locking in a stale or degenerate
    value if the bad export happened to land first in the file; keeping
    the LAST one instead favors whichever export happened most recently,
    which is the same "latest write wins" convention every other bridge
    file here already uses (live_state.csv, order_proposal.csv,
    hypothesis.txt are all overwritten in place, not appended to
    ambiguously). This never changes anything for a well-formed file with
    no duplicate dates.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        by_key: "OrderedDict[Tuple[str, date], DailyProfile]" = OrderedDict()
        for row in reader:
            profile = DailyProfile(
                instrument=row["instrument"],
                session_date=date.fromisoformat(row["date"]),
                val=float(row["val"]),
                vah=float(row["vah"]),
                poc=float(row["poc"]),
            )
            key = (profile.instrument, profile.session_date)
            by_key.pop(key, None)  # drop any earlier row for this key so re-inserting moves it to the end
            by_key[key] = profile
    return list(by_key.values())


def write_live_state(path: Path, state: LiveMarketState) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LIVE_STATE_FIELDS)
        writer.writerow(
            [
                state.timestamp.isoformat(),
                state.instrument,
                state.last_price,
                state.session_open,
                state.vwap_monthly,
                state.vwap_weekly,
                state.vwap_intraday,
                state.cum_delta,
                state.vwap_intraday_sd1,
                state.vwap_monthly_sd1,
                state.vwap_weekly_sd1,
            ]
        )


def _live_state_from_row(row: dict) -> LiveMarketState:
    return LiveMarketState(
        instrument=row["instrument"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        last_price=float(row["last_price"]),
        session_open=float(row["session_open"]),
        vwap_monthly=float(row["vwap_monthly"]),
        vwap_weekly=float(row["vwap_weekly"]),
        vwap_intraday=float(row["vwap_intraday"]),
        cum_delta=float(row["cum_delta"]),
        # .get, not row["..."] -- a historical_intraday.csv row logged
        # before this field existed won't have this column at all; treat
        # that the same as "not available" (0.0) rather than raising.
        vwap_intraday_sd1=float(row.get("vwap_intraday_sd1") or 0.0),
        vwap_monthly_sd1=float(row.get("vwap_monthly_sd1") or 0.0),
        vwap_weekly_sd1=float(row.get("vwap_weekly_sd1") or 0.0),
    )


def read_live_state(path: Path) -> Optional[LiveMarketState]:
    """Returns ``None`` if ACSIL hasn't written a snapshot yet (empty/missing rows).

    Only reads the first row: ``live_state.csv`` is overwritten in place on
    every refresh, so it only ever has one data row on the live side. For a
    historical *series* of snapshots (a backtest replay), use
    ``read_live_state_history`` instead.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
    if row is None:
        return None
    return _live_state_from_row(row)


def append_live_state(path: Path, state: LiveMarketState) -> None:
    """Appends one snapshot to a growing historical series.

    Unlike ``write_live_state`` (which overwrites in place -- the live
    single-row file ACSIL refreshes), this builds up the kind of file
    ``read_live_state_history`` reads for a backtest replay: writes the
    header only the first time (when ``path`` doesn't exist yet), then
    appends one row per call after that.
    """
    is_new = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(LIVE_STATE_FIELDS)
        writer.writerow(
            [
                state.timestamp.isoformat(),
                state.instrument,
                state.last_price,
                state.session_open,
                state.vwap_monthly,
                state.vwap_weekly,
                state.vwap_intraday,
                state.cum_delta,
                state.vwap_intraday_sd1,
                state.vwap_monthly_sd1,
                state.vwap_weekly_sd1,
            ]
        )


def read_live_state_history(path: Path) -> List[LiveMarketState]:
    """Reads every row as a chronological series of snapshots.

    Same column format as ``live_state.csv``, but meant for a file someone
    has appended to over time (a backtest's historical input), not the
    single-row file ACSIL overwrites live. Rows are returned in file order —
    callers that need chronological order should sort by ``.timestamp``
    themselves if the source file isn't already sorted.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [_live_state_from_row(row) for row in reader]


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


def _opt(value: Optional[float]) -> str:
    return "" if value is None else str(value)


def write_order_proposal(path: Path, snapshot: OrderProposalSnapshot) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(ORDER_PROPOSAL_FIELDS)
        writer.writerow(
            [
                snapshot.timestamp.isoformat(),
                snapshot.instrument,
                snapshot.direction,
                snapshot.hypothesis_type,
                snapshot.confluence,
                _opt(snapshot.entry),
                _opt(snapshot.stop),
                _opt(snapshot.target_1),
                _opt(snapshot.target_2),
                _opt(snapshot.runner),
                snapshot.contracts,
                snapshot.contracts_target1,
                snapshot.contracts_target2,
                snapshot.contracts_runner,
            ]
        )


def read_order_proposal(path: Path) -> Optional[OrderProposalSnapshot]:
    """Returns ``None`` if ACSIL/run_live.py hasn't written a snapshot yet
    (empty/missing rows) -- same convention as ``read_live_state``.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
    if row is None:
        return None
    return OrderProposalSnapshot(
        timestamp=datetime.fromisoformat(row["timestamp"]),
        instrument=row["instrument"],
        direction=row["direction"],
        hypothesis_type=row["hypothesis_type"],
        confluence=row["confluence"],
        entry=float(row["entry"]) if row["entry"] else None,
        stop=float(row["stop"]) if row["stop"] else None,
        target_1=float(row["target_1"]) if row["target_1"] else None,
        target_2=float(row["target_2"]) if row["target_2"] else None,
        runner=float(row["runner"]) if row["runner"] else None,
        contracts=int(row["contracts"]),
        contracts_target1=int(row["contracts_target1"]),
        contracts_target2=int(row["contracts_target2"]),
        contracts_runner=int(row["contracts_runner"]),
    )
