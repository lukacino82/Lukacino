"""
Swing system library = building blocks that are combined into a very large grid.

  REGIME filter  x  SETUP (entry trigger + entry mode)  x  EXIT model  x  DIRECTION

Every block is a small named function of the daily feature frame. New systems are added by
registering one more function in SETUPS / REGIMES / EXITS - the rest (grid, sieve, portfolio,
report) picks them up automatically.

Long setups are written once; the short version is the mirror image (see _mirror).
Sources of the classic rules (all published, decades of out-of-sample use):
  Connors & Alvarez  - RSI(2), cumulative RSI, ConnorsRSI, Double-7s, N down days, %b, limit
                       pullback entries ("Short Term Trading Strategies That Work", "High
                       Probability ETF Trading", "Buy the Fear, Sell the Greed")
  Larry Williams     - %R, turnaround days, Oops!, TDOM / turn-of-month ("Long-Term Secrets")
  Linda Raschke      - Holy Grail (ADX pullback), Turtle Soup, 80-20 ("Street Smarts")
  Toby Crabel        - NR7 / inside-day range expansion ("Day Trading with Short Term Price Patterns")
  Brian Shannon      - weekly / monthly / anchored VWAP reclaims ("Maximum Trading Gains with AVWAP")
  Dalton / Steidlmayer - value area: prior VAL / POC acceptance-rejection ("Mind over Markets")
  Ariel; Lakonishok & Smidt; Hirsch - turn-of-month and pre-holiday calendar effects
  Cooper, Cliff & Gulen; Lou-Polk-Skouras - overnight vs intraday return decomposition
  Faber / Antonacci  - long-term trend filters (10-month SMA, 200-day SMA)
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

INF = np.inf


# ======================================================================== regimes (long bias)
def regimes(d: pd.DataFrame) -> dict[str, np.ndarray]:
    c = d.close
    return {
        "any": np.ones(len(d), bool),
        "c>sma200": (c > d.sma200).values,
        "c>sma100": (c > d.sma100).values,
        "c>sma50": (c > d.sma50).values,
        "sma50>sma200": (d.sma50 > d.sma200).values,
        "c>qvwap": (c > d.qvwap).values,
        "c>prev_mvwap": (c > d.prev_mvwap).values,
        "c>sma200&dd<10": ((c > d.sma200) & (d.dd_ath > -0.10)).values,
        # bear regimes (for shorts)
        "c<sma200": (c < d.sma200).values,
        "c<sma50": (c < d.sma50).values,
        "sma50<sma200": (d.sma50 < d.sma200).values,
    }


LONG_REGIMES = ["any", "c>sma200", "c>sma100", "c>sma50", "sma50>sma200", "c>qvwap", "c>prev_mvwap", "c>sma200&dd<10"]
SHORT_REGIMES = ["any", "c<sma200", "c<sma50", "sma50<sma200"]


# ======================================================================== setups
# each returns list of (name, long_signal_bool, emode, lim_long, short_signal_bool, lim_short)
def setups(d: pd.DataFrame):
    c, h, l, o = d.close, d.high, d.low, d.open
    atr = d.atr20
    out = []

    def add(name, lsig, ssig=None, emode=0, llim=None, slim=None):
        out.append((name, np.asarray(lsig, bool),
                    None if ssig is None else np.asarray(ssig, bool), emode,
                    None if llim is None else np.asarray(llim, float),
                    None if slim is None else np.asarray(slim, float)))

    # --- A. oscillator mean reversion (Connors)
    for n, th in itertools.product((2, 3, 4, 5), (5, 10, 15, 20, 25, 30)):
        r = d[f"rsi{n}"]
        add(f"RSI{n}<{th}", r < th, r > 100 - th)
    for th in (10, 20, 35, 50):
        add(f"CumRSI2x2<{th}", d.crsi2_2 < th, d.crsi2_2 > 200 - th)
    for th in (30, 45, 60, 90):
        add(f"CumRSI2x3<{th}", d.crsi2_3 < th, d.crsi2_3 > 300 - th)
    for th in (5, 10, 15, 20, 25):
        add(f"ConnorsRSI<{th}", d.connors_rsi < th, d.connors_rsi > 100 - th)
    for th in (0.1, 0.15, 0.2, 0.25, 0.3):
        add(f"IBS<{th}", d.ibs < th, d.ibs > 1 - th)
    for th in (-0.1, 0.0, 0.1, 0.2):
        add(f"%b<{th}", d.bb_pctb < th, d.bb_pctb > 1 - th)
    for th in (-90, -95, -98):
        add(f"WR10<{th}", d.wr10 < th, d.wr10 > -100 - th)
    # --- B. price-action sequences
    for k in (2, 3, 4, 5):
        add(f"DownDays>={k}", d.downdays >= k, d.updays >= k)
        add(f"LowerLows>={k}", d.lower_lows >= k, d.higher_highs >= k)
    for n in (5, 7, 10, 20):
        add(f"CloseAt{n}dLow", d[f"ll{n}"], d[f"hh{n}"])
    for k in (1.0, 1.5, 2.0):
        add(f"BigDown>{k}ATR", d.ret < -k * atr, d.ret > k * atr)
        add(f"C<SMA5-{k}ATR", c < d.sma5 - k * atr, c > d.sma5 + k * atr)
    for k in (0.3, 0.6, 1.0):
        add(f"GapDownWeak>{k}ATR", (d.gap < -k * atr) & (d.ibs < 0.5), (d.gap > k * atr) & (d.ibs > 0.5))
    add("TurnaroundMon", (d.dow == 0) & (d.ret < 0), (d.dow == 0) & (d.ret > 0))
    for k in (2, 3):
        add(f"{k}DownIntoFri", (d.dow == 4) & (d.downdays >= k), (d.dow == 4) & (d.updays >= k))
    # --- C. VWAP family (weekly / monthly / quarterly / session)
    for vw in ("dvwap", "wvwap", "mvwap", "qvwap"):
        sd = d[vw + "_sd"]
        for k in (0.0, 0.5, 1.0, 1.5, 2.0):
            add(f"C<{vw}-{k}sd", c < d[vw] - k * sd, c > d[vw] + k * sd)
    for vw in ("wvwap", "mvwap"):
        # reclaim: close back above after close below the previous day
        add(f"Reclaim_{vw}", (c > d[vw]) & (c.shift() < d[vw].shift()), (c < d[vw]) & (c.shift() > d[vw].shift()))
    for ref in ("prev_wvwap", "prev_mvwap", "prev_qvwap"):
        add(f"C<{ref}", c < d[ref], c > d[ref])
        add(f"LowSweep_{ref}", (l < d[ref]) & (c > d[ref]), (h > d[ref]) & (c < d[ref]))
    # limit-order entries at VWAP bands next day (pullback into the level)
    for vw in ("wvwap", "mvwap"):
        sd = d[vw + "_sd"]
        for k in (0.0, 1.0, 2.0):
            lvl_l = d[vw] - k * sd
            lvl_s = d[vw] + k * sd
            add(f"LMT@{vw}-{k}sd", c > lvl_l, c < lvl_s, emode=2, llim=lvl_l, slim=lvl_s)
    # --- D. market profile (value area)
    add("C<prevDayVAL", c < d.val.shift(), c > d.vah.shift())
    add("C<prevWeekVAL", c < d.pw_val, c > d.pw_vah)
    add("C<prevWeekPOC", c < d.pw_poc, c > d.pw_poc)
    add("SweepPrevWeekVAL", (l < d.pw_val) & (c > d.pw_val), (h > d.pw_vah) & (c < d.pw_vah))
    add("LMT@prevWeekVAL", c > d.pw_val, c < d.pw_vah, emode=2, llim=d.pw_val, slim=d.pw_vah)
    # --- E. order flow (cumulative delta)
    for z in (-1.0, -1.5, -2.0):
        add(f"DeltaZ<{z}", d.delta_z < z, d.delta_z > -z)
    for n in (5, 10):
        add(f"Low{n}&CDpos", d[f"ll{n}"] & (d.cd5 > 0), d[f"hh{n}"] & (d.cd5 < 0))
    add("DownDay&DeltaPos", (d.ret < 0) & (d.eth_delta > 0), (d.ret > 0) & (d.eth_delta < 0))
    add("3Down&CD3pos", (d.downdays >= 3) & (d.cd3 > 0), (d.updays >= 3) & (d.cd3 < 0))
    add("BigDown&DeltaPos", (d.ret < -1.0 * d.atr20) & (d.eth_delta > 0), (d.ret > d.atr20) & (d.eth_delta < 0))
    # --- F. limit pullback entries (Connors) : buy next day k*ATR below today's close
    for n, th in ((2, 10), (2, 25), (3, 20)):
        for k in (0.25, 0.5, 0.75):
            r = d[f"rsi{n}"]
            add(f"LMT_RSI{n}<{th}_-{k}ATR", r < th, r > 100 - th, emode=2, llim=c - k * atr, slim=c + k * atr)
    for k in (0.25, 0.5):
        add(f"LMT_Down3_-{k}ATR", d.downdays >= 3, d.updays >= 3, emode=2, llim=c - k * atr, slim=c + k * atr)
    # --- G. calendar
    for k in (1, 2, 3, 4, 5):
        add(f"TOM_d-{k}", d.tdm_rev == k, None)       # enter at close of the k-th last trading day
    add("PreHoliday", pd.Series(d.pre_holiday.values, index=d.index).shift(-1).fillna(False).astype(bool), None)
    add("OpexWeekMon", d.opex_week & (d.dow == 0), None)
    # --- H. trend / breakout / continuation
    for n in (10, 20, 50):
        add(f"Breakout{n}dHigh", d[f"hh{n}"], d[f"ll{n}"])
        add(f"STOP@{n}dHigh", c > d.sma50, c < d.sma50, emode=3, llim=d[f"highN{n}"], slim=d[f"lowN{n}"])
    add("HolyGrail", (d.adx14 > 30) & (d.pdi > d.ndi) & (l <= d.ema21) & (c > d.ema21 * 0.99),
        (d.adx14 > 30) & (d.ndi > d.pdi) & (h >= d.ema21) & (c < d.ema21 * 1.01), emode=3, llim=h, slim=l)
    add("TurtleSoup20", (l < d.lowN20.shift()) & (c > d.lowN20.shift()), (h > d.highN20.shift()) & (c < d.highN20.shift()))
    nr7 = (h - l) <= (h - l).rolling(7).min()
    inside = (h < h.shift()) & (l > l.shift())
    add("NR7_BuyStop", nr7 & (c > d.sma50), nr7 & (c < d.sma50), emode=3, llim=h, slim=l)
    add("Inside_BuyStop", inside & (c > d.sma50), inside & (c < d.sma50), emode=3, llim=h, slim=l)
    add("EMA8>21cross", (d.ema8 > d.ema21) & (d.ema8.shift() <= d.ema21.shift()),
        (d.ema8 < d.ema21) & (d.ema8.shift() >= d.ema21.shift()))
    # --- I. multi-day drawdown from ATH buckets (structural buy-the-dip)
    for a, b in ((-0.03, -0.06), (-0.06, -0.10), (-0.10, -0.20)):
        add(f"ATH_DD{int(-a*100)}-{int(-b*100)}&Down", (d.dd_ath <= a) & (d.dd_ath > b) & (d.ret < 0), None)
    return out


# ======================================================================== exits
def exits(d: pd.DataFrame):
    """returns list of (name, dict of engine params, side-agnostic builder)"""
    n = len(d)
    c = d.close
    atr = d.atr20.values
    E = []

    def sig_exit(name, long_x, short_x, xmode=0, **kw):
        E.append((name, dict(kind="signal", lx=np.asarray(long_x, bool), sx=np.asarray(short_x, bool),
                             xmode=xmode, **kw)))

    # classic indicator exits (+ optional catastrophe stop and time stop)
    for cat in (None, 2.0, 3.0):
        for md in (0, 10):
            tag = ("" if cat is None else f"+SL{cat}ATR") + ("" if md == 0 else f"+T{md}")
            kw = {"sl_atr": cat, "max_days": md}
            sig_exit("x:C>SMA5" + tag, c > d.sma5, c < d.sma5, **kw)
            sig_exit("x:C>SMA3" + tag, c > d.sma3, c < d.sma3, **kw)
            sig_exit("x:C>PrevHigh" + tag, c > d.high.shift(), c < d.low.shift(), **kw)
            sig_exit("x:RSI2>70" + tag, d.rsi2 > 70, d.rsi2 < 30, **kw)
            sig_exit("x:FirstUpClose" + tag, d.ret > 0, d.ret < 0, **kw)
            sig_exit("x:C>SMA10" + tag, c > d.sma10, c < d.sma10, **kw)
            sig_exit("x:C>wvwap" + tag, c > d.wvwap, c < d.wvwap, **kw)
            sig_exit("x:IBS>0.8" + tag, d.ibs > 0.8, d.ibs < 0.2, **kw)
    sig_exit("x:C>SMA5@open", c > d.sma5, c < d.sma5, xmode=1)
    sig_exit("x:RSI2>50", d.rsi2 > 50, d.rsi2 < 50)
    sig_exit("x:RSI2>90", d.rsi2 > 90, d.rsi2 < 10)
    # pure time exits
    for md in (1, 2, 3, 4, 5, 7, 10, 15, 20):
        E.append((f"x:Time{md}", dict(kind="time", max_days=md)))
    # fixed points TP/SL and RRR
    for sl in (20, 30, 40, 60, 80, 100, 150):
        for rrr in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
            E.append((f"x:SL{sl}pt_RRR{rrr}", dict(kind="bracket", sl_pts=sl, tp_pts=sl * rrr, max_days=20)))
    # ATR brackets
    for sl in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        for rrr in (0.5, 1.0, 1.5, 2.0, 3.0):
            E.append((f"x:SL{sl}ATR_RRR{rrr}", dict(kind="bracket", sl_atr=sl, tp_atr=sl * rrr, max_days=20)))
    # trailing stops (chandelier) with initial ATR stop, optional time stop
    for tr in (1.0, 1.5, 2.0, 3.0, 4.0):
        for act in (0.0, 1.0):
            for md in (0, 20):
                E.append((f"x:Trail{tr}ATR_act{act}R" + ("" if md == 0 else f"_T{md}"),
                          dict(kind="trail", sl_atr=max(tr, 1.0), tr_atr=tr, tr_act=act, max_days=md)))
    # breakeven + RRR
    for sl in (1.0, 1.5):
        for rrr in (2.0, 3.0):
            E.append((f"x:SL{sl}ATR_RRR{rrr}_BE1R", dict(kind="bracket", sl_atr=sl, tp_atr=sl * rrr, be_r=1.0, max_days=20)))
    return E


def build_cfg(d, setup, exit_, side: int, regime_mask, cost):
    """combine one setup + exit + direction + regime into engine config"""
    name, lsig, ssig, emode, llim, slim = setup
    ename, ex = exit_
    n = len(d)
    sig = lsig if side > 0 else ssig
    if sig is None:
        return None
    sig = sig & regime_mask
    s = np.where(np.nan_to_num(sig, nan=False), side, 0).astype(np.int8)
    atr = d.atr20.values
    cfg = {"side": s, "emode": emode, "cost": cost}
    lim = llim if side > 0 else slim
    if lim is not None:
        cfg["lim"] = np.nan_to_num(lim, nan=0.0)
        # never let a limit/stop with missing level fire
        s[np.isnan(lim)] = 0
    inf = np.full(n, INF)
    kind = ex["kind"]
    sl = inf
    tp = inf
    tr = inf
    if ex.get("sl_atr"):
        sl = ex["sl_atr"] * atr
    if ex.get("sl_pts"):
        sl = np.full(n, float(ex["sl_pts"]))
    if ex.get("tp_atr"):
        tp = ex["tp_atr"] * atr
    if ex.get("tp_pts"):
        tp = np.full(n, float(ex["tp_pts"]))
    if ex.get("tr_atr"):
        tr = ex["tr_atr"] * atr
    cfg.update(sl=np.nan_to_num(sl, nan=INF), tp=np.nan_to_num(tp, nan=INF), tr=np.nan_to_num(tr, nan=INF),
               tr_act=ex.get("tr_act", 0.0), be_r=ex.get("be_r", 0.0), max_days=ex.get("max_days", 0))
    if kind == "signal":
        x = ex["lx"] if side > 0 else ex["sx"]
        cfg["xsig"] = np.where(x, side, 0).astype(np.int8)
        cfg["xmode"] = ex.get("xmode", 0)
    return cfg
