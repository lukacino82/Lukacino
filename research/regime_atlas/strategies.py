"""Regime Atlas: one daily return series per strategy tested in this repository.

Everything is expressed as daily return on 1x ES notional (back-adjusted ES2008 data), so strategies
can be compared with buy & hold day by day. Daily rules decide at the close of day t and hold over the
next session (close-to-close), costs 0.5 point per unit change of position. Intraday systems come
from the existing research outputs (mattia, alpha_test), converted from points to % of prior close.
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "swing_alpha"))
from signals import table, build_signals  # noqa: E402

OUT = os.path.join(HERE, "out")
COST_PT = 0.5

# family, mechanism (the "loaded dice" behind the rule), short description
META = {
    "B&H": ("Benchmark", "Riziková prémie akcií + politická podpora trhu (wealth effect)", "Long ES pořád"),
    "MA200 long/flat": ("Trend / expozice", "Trendy trvají kvůli pomalé reakci investorů a CTA tokům; mimo trend se vyhne medvědím trhům", "Long nad 200denním průměrem, jinak hotovost"),
    "MA200 long/short": ("Trend / expozice", "Totéž + short v downtrendu", "Long nad MA200, short pod"),
    "TSMOM 12M": ("Trend / expozice", "Časové momentum: pozitivní 12M výnos pokračuje (CTA, herding)", "Long když je 12M výnos > 0"),
    "Donchian 55/20": ("Trend / expozice", "Breakout nových maxim, výstup na 20denním minimu", "Long po 55D maximu, ven pod 20D minimem"),
    "EMA20>50 + ADX>25": ("Trend / expozice", "Silný trend podle ADX", "Long když EMA20>EMA50 a ADX>25"),
    "Vol target 15 %": ("Volatilita / expozice", "Volatilita je předvídatelná a vysoká vol = horší poměr výnos/riziko (vol-managed portfolia)", "Páka 15 % / realizovaná vol 20D, max 2x"),
    "Vol-managed B&H": ("Volatilita / expozice", "Totéž, verze z ES Alpha Map", "Expozice podle volatility, cap 2x"),
    "Bez vysoké vol": ("Volatilita / expozice", "Ve volatilním režimu je Sharpe ES nejhorší", "Long, jen když 20D vol není v horním kvintilu roku"),
    "Crisis allocator": ("Volatilita / expozice", "Přikupování v korekcích s potvrzením: po panice přichází nucené zpětné nákupy", "Přidává 0,5x vrstvy po poklesu −3 % s potvrzením"),
    "52T max = poloviční páka": ("Volatilita / expozice", "Po novém 52T maximu ES roste pomaleji (Edge Factory)", "0,5x expozice 20 dní po novém 52T maximu, jinak 1x"),
    "RSI(2) < 10": ("Reverze", "Krátkodobá přeprodanost: likvidita poskytnutá panickým prodejcům je odměněna", "Long při RSI(2)<10, ven při RSI(2)>70 nebo po 10 dnech"),
    "RSI(2) L/S": ("Reverze", "Totéž oboustranně", "Long RSI(2)<10, short RSI(2)>90"),
    "IBS<0.2 bull": ("Reverze", "Close u low dne v býčím trhu → odraz", "Long po close v dolních 20 % rozpětí, jen nad MA200"),
    "3 dny dolů": ("Reverze", "Série poklesů v býčím trhu = přeprodanost", "Long po 3 poklesech v řadě, drž 5 dní"),
    "Jádro fade 10D": ("Reverze", "Fade bearish extrémů (Swing Alpha): breakdown kompozitu, bear zarovnání VWAP", "Long po bearish extrému, drž 10 dní"),
    "5D reverze L/S": ("Reverze", "Kontrariánská krátkodobá reverze", "Pozice proti směru 5denního pohybu"),
    "VWAP D/W/M zarovnání": ("Struktura / VWAP / profil", "SW02: všechny VWAPy pod cenou = trend pokračuje", "Long když close > denní, týdenní i měsíční VWAP"),
    "Breakout z kompozitu": ("Struktura / VWAP / profil", "SW03: akceptace mimo value area kompozitu", "Long 5 dní po close nad VAH kompozitu"),
    "Migrace POC": ("Struktura / VWAP / profil", "SW01: hodnota migruje nahoru", "Long 5 dní po 2 dnech rostoucího POC a VA"),
    "Bull režim": ("Struktura / VWAP / profil", "SW04: persistence režimu", "Long v Bull režimu"),
    "Overnight hold": ("Kalendář / toky", "Noční prémie: riziko gapů nese ten, kdo drží přes noc", "Long od RTH close do RTH open každý den"),
    "Intraday hold": ("Kalendář / toky", "Opak: jen denní seance", "Long od RTH open do RTH close"),
    "Turn of month": ("Kalendář / toky", "Toky mezd/penzijních příspěvků na přelomu měsíce", "Long kolem přelomu měsíce"),
    "Pre-FOMC": ("Kalendář / toky", "Drift před rozhodnutím Fedu", "Long 24 h před FOMC"),
    "S3 Overnight Bias": ("Intraday systémy", "Směr noční seance pokračuje v RTH (Mattia)", "Intraday podle overnight biasu"),
    "S1 Vault Break": ("Intraday systémy", "Breakout prop-firm geometrie (Mattia)", "Intraday breakout s malým TP/SL"),
    "S2 VWAP Pullback": ("Intraday systémy", "Pullback na VWAP s ADX (Mattia)", "Intraday pullback"),
    "Noise-area momentum": ("Intraday systémy", "Průraz denní šumové zóny = informovaný tok (Zarattini)", "Intraday momentum L/S"),
    "Deep gap + VWAP + delta div": ("Intraday systémy", "Panický gap dolů + absorpce (alpha brainstorm)", "Intraday long po hlubokém gapu"),
    "DD2 PDL sweep": ("Intraday systémy", "Sweep předchozího low v býčím trhu (alpha brainstorm)", "Intraday long po sweepu PDL"),
    "Bull 10–12 delta div": ("Intraday systémy", "Delta divergence dopoledne (alpha brainstorm)", "Intraday long"),
    "Morning VWAP + volume": ("Intraday systémy", "ChatGPT Phase 2 favorit (nereplikoval se)", "Intraday"),
}


def hold_mask(sig, n):
    """position 1 for n days after each signal (signal at close t -> held over days t+1..t+n)"""
    s = np.asarray(sig, bool)
    pos = np.zeros(len(s))
    left = 0
    for i in range(len(s)):
        if left > 0:
            pos[i] = 1
            left -= 1
        if s[i]:
            left = n
    return pos  # pos[i] is exposure decided at close i-1 ... aligned below with shift


def build():
    T = table()
    D = pd.read_parquet("/tmp/claude-0/data/daily_series.parquet")
    D.index = pd.to_datetime(D.index)
    D = D.reindex(T.index).fillna(0.0)
    r = D["B&H"]                                   # close-to-close ES return (as used in ES Alpha Map)
    C = T.C; pc = T.gC.shift()
    S = {}

    def daily(pos, name):
        """pos decided at close t (series aligned to t), applied to r[t+1]"""
        p = pd.Series(pos, index=T.index).fillna(0.0)
        turn = p.diff().abs().fillna(p.abs())
        S[name] = p.shift().fillna(0) * r - turn.shift().fillna(0) * COST_PT / pc.fillna(C)

    S["B&H"] = r
    daily((C > T.ma200).astype(float), "MA200 long/flat")
    daily(np.where(T.ma200.isna(), 0, np.where(C > T.ma200, 1.0, -1.0)), "MA200 long/short")
    daily((C > C.shift(252)).astype(float), "TSMOM 12M")
    don = np.zeros(len(T)); state = 0
    hi55 = T.hi55.shift().to_numpy(); lo20 = T.lo20.shift().to_numpy(); c = C.to_numpy()
    for i in range(len(T)):
        if state == 0 and c[i] > hi55[i]:
            state = 1
        elif state == 1 and c[i] < lo20[i]:
            state = 0
        don[i] = state
    daily(don, "Donchian 55/20")
    daily(((T.ema20 > T.ema50) & (T.adx14 > 25)).astype(float), "EMA20>50 + ADX>25")
    daily(np.clip(0.15 / T.rv20.clip(lower=0.03), 0, 2).fillna(1), "Vol target 15 %")
    S["Vol-managed B&H"] = D["Vol-managed B&H"]
    daily((T.rv_rank.fillna(0.5) <= 0.8).astype(float), "Bez vysoké vol")
    S["Crisis allocator"] = D["Crisis allocator (-3%, 0.5x, 2 vrstvy)"]
    new_hi = (T.H >= T.H.rolling(252, min_periods=200).max()).to_numpy()
    after = hold_mask(new_hi, 20)  # 1 during the 20 days after a new high
    after = np.maximum(after, new_hi)
    daily(np.where(after > 0, 0.5, 1.0), "52T max = poloviční páka")

    rsi = T.rsi2.to_numpy(); pos = np.zeros(len(T)); age = 0
    for i in range(len(T)):
        if pos[i - 1] if i else 0:
            age += 1
            pos[i] = 0 if (rsi[i] > 70 or age >= 10) else 1
        else:
            pos[i] = 1 if rsi[i] < 10 else 0
            age = 0
    daily(pos, "RSI(2) < 10")
    daily(np.where(T.rsi2 < 10, 1.0, np.where(T.rsi2 > 90, -1.0, 0.0)), "RSI(2) L/S")
    S["IBS<0.2 bull"] = D["IBS<0.2 bull"]
    dn3 = (T.ret < 0) & (T.ret.shift() < 0) & (T.ret.shift(2) < 0)
    daily(np.r_[hold_mask(dn3.to_numpy(), 5)[1:], 0], "3 dny dolů")
    sig = build_signals(T)
    core = ["CB2 · close za High/Low kompozitu", "CB3 · retest prolomené hrany", "V3 · V2 + sklon M", "skóre 90–100"]
    m = np.zeros(len(T), bool)
    for fam, nm, sd, mask in sig:
        if sd == -1 and nm in core:
            m |= mask
    daily(np.r_[hold_mask(m, 10)[1:], 0], "Jádro fade 10D")
    daily(-np.sign(C - C.shift(5)).fillna(0), "5D reverze L/S")
    get = {(nm, sd): mask for fam, nm, sd, mask in sig}
    daily(get[("V1 · D/W/M zarovnáno", 1)].astype(float), "VWAP D/W/M zarovnání")
    daily(np.r_[hold_mask(get[("CB1 · close za VAH/VAL kompozitu", 1)], 5)[1:], 0], "Breakout z kompozitu")
    daily(np.r_[hold_mask(get[("C · POC + střed VA 2 dny", 1)], 5)[1:], 0], "Migrace POC")
    daily((T.regime == "Bull").astype(float), "Bull režim")
    # overnight vs intraday split (RTH close -> next RTH open, and RTH open -> close)
    S["Overnight hold"] = ((T.O - C.shift()) / C.shift()).fillna(0) - COST_PT / C
    S["Intraday hold"] = ((C - T.O) / C.shift()).fillna(0) - COST_PT / C
    S["Turn of month"] = D["Turn of month"]
    S["Pre-FOMC"] = D["Pre-FOMC"]
    S["S3 Overnight Bias"] = D["S3 Overnight Bias"]
    S["S1 Vault Break"] = D["S1 Vault Break"]
    S["S2 VWAP Pullback"] = D["S2 VWAP Pullback"]
    S["Noise-area momentum"] = D["Noise-area momentum L/S"]
    at = pickle.load(open(os.path.join(ROOT, "alpha_test/out/series.pkl"), "rb"))["eq"]
    for key, name in (("Q_DeepGap_VWAP_DeltaDiv", "Deep gap + VWAP + delta div"), ("DD2_AboveMA200_PDL_Sweep", "DD2 PDL sweep"),
                      ("Q_Bull_10_12_DeltaDiv", "Bull 10–12 delta div"), ("Q_Morning_VWAP_Volume", "Morning VWAP + volume")):
        e = at[key].copy(); e["date"] = pd.to_datetime(e["date"])
        pts = e.groupby("date").net.sum()
        x = (pts / pc.reindex(pts.index)).reindex(T.index).fillna(0.0)
        x[T.index < pd.Timestamp("2018-07-09")] = np.nan          # alpha_test data starts 2018-07
        S[name] = x
    R = pd.DataFrame(S)
    R = R[R.index >= "2009-01-02"]
    return R, T


if __name__ == "__main__":
    R, T = build()
    R.to_parquet(os.path.join(OUT, "returns.parquet"))
    pd.set_option("display.width", 200)
    eq = (1 + R.fillna(0)).prod()
    print(pd.DataFrame({"x": eq.round(2), "ann_vol": (R.std() * np.sqrt(252)).round(3), "n": R.count()}).to_string())
