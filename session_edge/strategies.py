"""Logiky vstupů postavené na nejvolatilnějších časových oknech seance.

Každá strategie dostane jeden obchodní den (bary v její časové zóně) a
kontext spočítaný jen z minulých dní (ATR, včerejší close). Vrací seznam
kandidátních vstupů `Signal`. O velikosti SL/TP, počtu obchodů a nuceném
zavření rozhoduje až engine podle `RiskConfig`.

Konvence: timestamp baru = čas jeho otevření. Okno [start, end) obsahuje bary
s časem otevření >= start a < end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Literal, Optional

import numpy as np
import pandas as pd

from .config import parse_time

Fill = Literal["intrabar", "close", "open"]


@dataclass
class DayContext:
    date: object
    atr: float
    prev_close: Optional[float]
    prev_range: Optional[float]


@dataclass
class Signal:
    bar_pos: int  # pozice baru (v rámci dne), na kterém dochází ke vstupu
    direction: int  # +1 long, -1 short
    entry: float
    stop: float  # „přirozený“ stop navržený strategií
    ref_range: float  # referenční range (pro stop_mode="range")
    fill: Fill  # intrabar = stop order uvnitř baru, close = na close baru, open = na open
    tag: str = ""


def _window(day: pd.DataFrame, start: time, end: time) -> np.ndarray:
    t = day.index.time
    if start <= end:
        return (t >= start) & (t < end)
    return (t >= start) | (t < end)  # okno přes půlnoc


@dataclass
class Strategy:
    tz: str = "America/New_York"
    name: str = "base"

    def generate(self, day: pd.DataFrame, ctx: DayContext) -> list[Signal]:  # pragma: no cover
        raise NotImplementedError

    def params(self) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            out[k] = v.strftime("%H:%M") if isinstance(v, time) else v
        return out


# ---------------------------------------------------------------------------
# A) Průraz rangu (Opening Range Breakout / Asijský range → London open)
# ---------------------------------------------------------------------------
@dataclass
class RangeBreakout(Strategy):
    """Průraz rangu vytvořeného v úvodu seance (nebo v klidné předchozí seanci).

    Hypotéza: otevření hlavní seance přináší koncentrovaný order-flow
    (institucionální rebalancování, reakce na overnight zprávy). Když cena
    opustí úvodní range, informace se teprve začíná promítat do ceny →
    krátkodobý momentum efekt. Filtr `max_range_atr` bere jen dny, kdy byl
    range úzký vůči ATR (komprese → expanze volatility).
    """

    name: str = "range_breakout"
    range_start: time | str = "09:30"
    range_end: time | str = "10:00"
    entry_end: time | str = "12:00"
    stop_at: Literal["opposite", "mid"] = "opposite"
    buffer_atr: float = 0.0  # průraz musí přesáhnout range o buffer × ATR
    min_range_atr: float = 0.0
    max_range_atr: float = 10.0
    direction: Literal["both", "long", "short"] = "both"

    def __post_init__(self) -> None:
        self.range_start = parse_time(self.range_start)
        self.range_end = parse_time(self.range_end)
        self.entry_end = parse_time(self.entry_end)

    def generate(self, day: pd.DataFrame, ctx: DayContext) -> list[Signal]:
        rmask = _window(day, self.range_start, self.range_end)
        if not rmask.any():
            return []
        rh = day["high"].values[rmask].max()
        rl = day["low"].values[rmask].min()
        rng = rh - rl
        if rng <= 0 or not (self.min_range_atr * ctx.atr <= rng <= self.max_range_atr * ctx.atr):
            return []
        buf = self.buffer_atr * ctx.atr
        up, dn = rh + buf, rl - buf
        mid = (rh + rl) / 2

        last_range_pos = np.flatnonzero(rmask)[-1]
        emask = _window(day, self.range_end, self.entry_end)
        emask[: last_range_pos + 1] = False
        pos = np.flatnonzero(emask)
        o, h, l = day["open"].values, day["high"].values, day["low"].values

        long_pos = next((p for p in pos if h[p] >= up), None)
        short_pos = next((p for p in pos if l[p] <= dn), None)
        # outside bar prorazí obě strany – pořadí neznáme, takový bar vynecháme
        if long_pos is not None and long_pos == short_pos:
            return []

        out = []
        if long_pos is not None and self.direction in ("both", "long"):
            e = max(up, o[long_pos])
            s = rl if self.stop_at == "opposite" else mid
            out.append(Signal(long_pos, 1, e, s, rng, "intrabar", "breakout_long"))
        if short_pos is not None and self.direction in ("both", "short"):
            e = min(dn, o[short_pos])
            s = rh if self.stop_at == "opposite" else mid
            out.append(Signal(short_pos, -1, e, s, rng, "intrabar", "breakout_short"))
        return sorted(out, key=lambda x: x.bar_pos)


# ---------------------------------------------------------------------------
# B) Falešný průraz rangu – fade (liquidity sweep / „turtle soup“)
# ---------------------------------------------------------------------------
@dataclass
class FailedBreakoutFade(Strategy):
    """Cena vybere likviditu nad/pod rangem (stopky), ale uzavře bar zpět uvnitř.

    Hypotéza: průraz byl tažen stop-lossy a ne novou informací; po vybrání
    likvidity se cena vrací k rovnovážné hodnotě rangu. Vstup proti průrazu
    na close baru, který se vrátil do rangu; stop za extrémem průrazu.
    """

    name: str = "failed_breakout_fade"
    range_start: time | str = "09:30"
    range_end: time | str = "10:00"
    entry_end: time | str = "13:00"
    min_excursion_atr: float = 0.05  # jak daleko musí průraz dojít
    stop_buffer_atr: float = 0.02
    min_range_atr: float = 0.0
    max_range_atr: float = 10.0

    def __post_init__(self) -> None:
        self.range_start = parse_time(self.range_start)
        self.range_end = parse_time(self.range_end)
        self.entry_end = parse_time(self.entry_end)

    def generate(self, day: pd.DataFrame, ctx: DayContext) -> list[Signal]:
        rmask = _window(day, self.range_start, self.range_end)
        if not rmask.any():
            return []
        rh = day["high"].values[rmask].max()
        rl = day["low"].values[rmask].min()
        rng = rh - rl
        if rng <= 0 or not (self.min_range_atr * ctx.atr <= rng <= self.max_range_atr * ctx.atr):
            return []
        exc = self.min_excursion_atr * ctx.atr
        buf = self.stop_buffer_atr * ctx.atr
        last_range_pos = np.flatnonzero(rmask)[-1]
        emask = _window(day, self.range_end, self.entry_end)
        emask[: last_range_pos + 1] = False
        h, l, c = day["high"].values, day["low"].values, day["close"].values

        out: list[Signal] = []
        hi_ext, lo_ext = -np.inf, np.inf
        short_done = long_done = False
        for p in np.flatnonzero(emask):
            hi_ext = max(hi_ext, h[p])
            lo_ext = min(lo_ext, l[p])
            if not short_done and hi_ext >= rh + exc and c[p] < rh:
                out.append(Signal(p, -1, c[p], hi_ext + buf, rng, "close", "fade_short"))
                short_done = True
            if not long_done and lo_ext <= rl - exc and c[p] > rl:
                out.append(Signal(p, 1, c[p], lo_ext - buf, rng, "close", "fade_long"))
                long_done = True
            if short_done and long_done:
                break
        return sorted(out, key=lambda x: x.bar_pos)


# ---------------------------------------------------------------------------
# C) Intradenní momentum: první půlhodina predikuje poslední půlhodinu
# ---------------------------------------------------------------------------
@dataclass
class IntradayMomentum(Strategy):
    """Gao, Han, Li, Zhou (2018), *Market Intraday Momentum*, JFE.

    Výnos od včerejšího close do konce první půlhodiny predikuje znaménko
    výnosu poslední půlhodiny (obě okna jsou nejvolatilnější části U-profilu).
    Mechanismus: rebalancování hedgerů gamma pozic a pozdní obchodníci, kteří
    dorovnávají pozici před zavřením. Vstup v `entry_time`, výstup na konci
    seance (nastavte `RiskConfig.exit_time`, nebo nechte do posledního baru).
    """

    name: str = "intraday_momentum"
    signal_start: time | str = "09:30"
    signal_end: time | str = "10:00"
    entry_time: time | str = "15:30"
    include_overnight: bool = True
    min_move_atr: float = 0.0  # ignorovat bezvýznamně malé pohyby
    stop_atr: float = 0.5  # přirozený stop (katastrofický) v násobcích ATR

    def __post_init__(self) -> None:
        self.signal_start = parse_time(self.signal_start)
        self.signal_end = parse_time(self.signal_end)
        self.entry_time = parse_time(self.entry_time)

    def generate(self, day: pd.DataFrame, ctx: DayContext) -> list[Signal]:
        smask = _window(day, self.signal_start, self.signal_end)
        if not smask.any():
            return []
        spos = np.flatnonzero(smask)
        base = (
            ctx.prev_close
            if self.include_overnight and ctx.prev_close is not None
            else day["open"].values[spos[0]]
        )
        move = day["close"].values[spos[-1]] - base
        if abs(move) < self.min_move_atr * ctx.atr or move == 0:
            return []
        t = day.index.time
        cand = np.flatnonzero((t >= self.entry_time) & (np.arange(len(day)) > spos[-1]))
        if len(cand) == 0:
            return []
        p = cand[0]
        d = 1 if move > 0 else -1
        e = day["open"].values[p]
        return [Signal(p, d, e, e - d * self.stop_atr * ctx.atr, abs(move), "open", "momentum")]


# ---------------------------------------------------------------------------
# D) Fade přepáleného gapu na otevření
# ---------------------------------------------------------------------------
@dataclass
class GapFade(Strategy):
    """Velký overnight gap (vůči ATR) bez pokračování v první půlhodině se
    často částečně zavírá. Vstup proti gapu po `confirm_end`, pokud cena
    během potvrzovacího okna nepokračovala dál ve směru gapu (tj. close
    potvrzovacího okna je zpět za open seance). Stop za extrémem okna."""

    name: str = "gap_fade"
    session_open: time | str = "09:30"
    confirm_end: time | str = "10:00"
    min_gap_atr: float = 0.3
    max_gap_atr: float = 1.5  # obří gapy (zprávy) nefadujeme

    def __post_init__(self) -> None:
        self.session_open = parse_time(self.session_open)
        self.confirm_end = parse_time(self.confirm_end)

    def generate(self, day: pd.DataFrame, ctx: DayContext) -> list[Signal]:
        if ctx.prev_close is None:
            return []
        cmask = _window(day, self.session_open, self.confirm_end)
        if not cmask.any():
            return []
        cpos = np.flatnonzero(cmask)
        o = day["open"].values[cpos[0]]
        gap = o - ctx.prev_close
        if not (self.min_gap_atr * ctx.atr <= abs(gap) <= self.max_gap_atr * ctx.atr):
            return []
        c_end = day["close"].values[cpos[-1]]
        d = -1 if gap > 0 else 1
        if d == -1 and c_end >= o:  # gap nahoru a cena dál roste -> nefadovat
            return []
        if d == 1 and c_end <= o:
            return []
        stop = day["high"].values[cpos].max() if d == -1 else day["low"].values[cpos].min()
        return [Signal(cpos[-1], d, c_end, stop, abs(gap), "close", "gap_fade")]


# ---------------------------------------------------------------------------
# Předvolby pro konkrétní trhy / seance
# ---------------------------------------------------------------------------
PRESETS: dict[str, callable] = {
    # US indexy (ES, NQ, SPY, QQQ) – ORB 30 min po otevření NYSE
    "us_orb30": lambda: RangeBreakout(tz="America/New_York", range_start="09:30",
                                      range_end="10:00", entry_end="12:00"),
    # ORB 5 min (Zarattini & Aziz 2023 – variantu testovali na QQQ)
    "us_orb5": lambda: RangeBreakout(tz="America/New_York", range_start="09:30",
                                     range_end="09:35", entry_end="11:00"),
    # FX / zlato – asijský range 00:00–07:00 Londýn, průraz na London open
    "london_asia_breakout": lambda: RangeBreakout(tz="Europe/London", range_start="00:00",
                                                  range_end="07:00", entry_end="10:00"),
    # NY open na FX/zlatě – range první hodiny Londýna/NY overlapu
    "ny_overlap_breakout": lambda: RangeBreakout(tz="America/New_York", range_start="08:00",
                                                 range_end="08:30", entry_end="11:00"),
    "us_orb_fade": lambda: FailedBreakoutFade(tz="America/New_York"),
    "london_sweep_fade": lambda: FailedBreakoutFade(tz="Europe/London", range_start="00:00",
                                                    range_end="07:00", entry_end="11:00"),
    "us_intraday_momentum": lambda: IntradayMomentum(tz="America/New_York"),
    "us_gap_fade": lambda: GapFade(tz="America/New_York"),
}

STRATEGY_CLASSES = {
    "range_breakout": RangeBreakout,
    "failed_breakout_fade": FailedBreakoutFade,
    "intraday_momentum": IntradayMomentum,
    "gap_fade": GapFade,
}


def make_strategy(name: str, **overrides) -> Strategy:
    """Vytvoří strategii z předvolby (PRESETS) nebo třídy, s přepsanými parametry."""
    if name in PRESETS:
        base = PRESETS[name]()
        params = {**base.__dict__, **overrides}
        return type(base)(**params)
    if name in STRATEGY_CLASSES:
        return STRATEGY_CLASSES[name](**overrides)
    raise KeyError(f"Neznámá strategie '{name}'. Dostupné: {sorted(PRESETS) + sorted(STRATEGY_CLASSES)}")
