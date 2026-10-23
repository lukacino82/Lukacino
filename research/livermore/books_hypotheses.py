"""All testable hypotheses from the three books in the Drive folder, on ES daily data 2009-2026.

Sources: J. Livermore "How to Trade in Stocks" (1940) = HTTIS; R. D. Wyckoff "Jesse Livermore's Methods of Trading in
Stocks" = WY; Trade Navigator "Livermore Lines" manual (top-down market/industry/tandem filter - needs several
markets, not testable on ES alone).

Livermore's point thresholds are for stocks priced 30-100 USD (6 points ~ 6-20 %, 3 points ~ half of it). On ES they
are scaled with the previous day's ATR(14) (~1.3 % of price) or with %.

  H1  HTTIS ch.1/5  pivotal breakout from a consolidation: 20-day range <= 3 ATR, close above the 20-day closing high
  H2  HTTIS ch.5    round-number pivotal point: first close above a new 100-point level (only 2018+ raw prices)
  H3  HTTIS ch.1    buy a new high after a normal reaction (uptrend, pullback >= 1.5 ATR within 10 days, new 20D high)
  H4  HTTIS ch.1    "never buy on reactions": the opposite - uptrend, close >= 1.5 ATR below the 20-day high (control)
  H5  HTTIS ch.2    danger signal = abnormal reaction: after a 20-day rise >= 4 ATR, a day closing >= 1.5 ATR below
                    its own high -> should be followed by weakness (exit signal)
  H6  HTTIS ch.2    normal reactions come on lower volume: uptrend down day with volume < 0.8 x 20-day average
                    -> long; control: down day with volume > 1.2 x average
  H7  HTTIS ch.5    pivotal point test: after a down trend low L, a rally of >= 2 ATR, a reaction that holds within
                    0.5 ATR of L, then a 0.5 ATR rally from that reaction low -> buy
  H8  HTTIS ch.1    "never buy because of a big decline": 20-day drop >= 3 / 5 ATR -> long should NOT pay
  H9  WY ch.8       panic buying ("playing for position"): 20-day drop >= 5 ATR and volume >= 1.5 x average -> long
  H10 WY ch.4       intermediate swings: sell when overbought (close >= 20-day mean + 2.5 ATR), buy back lower ->
                    forward return after overbought should be below average (exit signal)
  H11 WY ch.5/6     minimum profit 10 points vs 3-4 points risk + time stop of a few days: H1/H3 entries with
                    stop 1 ATR / target 3 ATR / exit after 10 days vs plain 20-day hold
  H12 HTTIS ch.6    pyramiding 1/5 at each higher price and WY limited pyramid (1/3, double, complete) - see
                    livermore.py (tested: worse than a full position on ES)
  H13 HTTIS ch.8-9  Market Key with % thresholds (6 points on a 60 USD stock ~ 10 %): 5 / 8 / 10 %, pivot
                    confirmation half of it - see market_key_pct()
Event study: entry at the next open, exit at the close after h = 5, 10, 20, 60 days, in ATR; excess = minus the
average of all days of the same year (removes the ES drift); non-overlapping signals; periods 2009-17, 18-21, 22-26.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
from livermore import run_pos, perf  # noqa: E402

OUT = os.path.join(HERE, "out")
HS = (5, 10, 20, 60)


def load():
    import features as F
    T = F.load()["T"][["O", "H", "L", "C", "vol", "ATR", "ma200", "ema50"]].copy()
    T["A"] = T.ATR.shift()
    return T.loc["2008-09":]


def signals(T):
    C, H, L, V, A = T.C, T.H, T.L, T.vol, T.A
    up = (C > T.ma200) & (C > T.ema50)
    hi20 = C.rolling(20).max(); rng20 = H.rolling(20).max() - L.rolling(20).min()
    v20 = V.rolling(20).mean()
    S = {}
    S["H1 průraz z konsolidace (20D rozsah ≤ 3 ATR)"] = ((rng20.shift() <= 3 * A) & (C > C.shift().rolling(20).max()), 1)
    dd10 = (C.rolling(20).max() - C).rolling(10).max()
    S["H3 nové maximum po normální reakci (≥1,5 ATR)"] = (up & (dd10.shift() >= 1.5 * A) & (C >= hi20) & (C.shift() < hi20.shift()), 1)
    S["H4 nákup v reakci (kontrola: ≥1,5 ATR pod 20D max)"] = (up & (C <= hi20 - 1.5 * A) & (C.shift() > hi20.shift() - 1.5 * A), 1)
    S["H5 abnormální reakce po růstu (exit signál)"] = (((C - C.shift(20)) >= 4 * A) & ((H - C) >= 1.5 * A), 1)
    S["H6 reakce na nízkém objemu (<0,8×)"] = (up & (C < C.shift()) & (V < 0.8 * v20), 1)
    S["H6 kontrola: reakce na vysokém objemu (>1,2×)"] = (up & (C < C.shift()) & (V > 1.2 * v20), 1)
    S["H7 test pivotu (dvojité dno)"] = (pd.Series(pivot_test(T), index=T.index), 1)
    S["H8 po velkém poklesu 20D ≥ 3 ATR"] = (((C.shift(20) - C) >= 3 * A) & ((C.shift(21) - C.shift(1)) < 3 * A), 1)
    S["H8 po velkém poklesu 20D ≥ 5 ATR"] = (((C.shift(20) - C) >= 5 * A) & ((C.shift(21) - C.shift(1)) < 5 * A), 1)
    S["H9 panika: pokles ≥ 5 ATR + objem ≥ 1,5×"] = (((C.shift(20) - C) >= 5 * A) & (V >= 1.5 * v20), 1)
    S["H10 překoupenost: close ≥ 20D průměr + 2,5 ATR (exit signál)"] = ((C >= C.rolling(20).mean() + 2.5 * A), 1)
    S["Referenční: nové 20D maximum (bez podmínek)"] = ((C >= hi20) & (C.shift() < hi20.shift()), 1)
    return S


def pivot_test(T, up_thr=2.0, hold=0.5, conf=0.5):
    """L = swing low after a decline; rally >= up_thr ATR; reaction low L2 with |L2 - L| <= hold ATR (not breaking
    L by more than hold); buy when close >= L2 + conf ATR. One signal per pattern."""
    c, a = T.C.to_numpy(), T.A.to_numpy()
    n = len(c); sig = np.zeros(n, bool)
    state = 0; L = np.inf; Hh = -np.inf; L2 = np.inf; rlo = np.inf
    for t in range(1, n):
        if not np.isfinite(a[t]):
            continue
        if state == 0:                       # tracking a low
            if c[t] < L:
                L = c[t]
            elif c[t] >= L + up_thr * a[t]:
                state = 1; Hh = c[t]; rlo = np.inf
        elif state == 1:                     # rally, waiting for the reaction back towards L
            if c[t] > Hh:
                if Hh - rlo >= up_thr * a[t]:  # a full reaction that held higher -> it becomes the new swing low
                    L = rlo
                Hh = c[t]; rlo = np.inf
            rlo = min(rlo, c[t])
            if c[t] < L - hold * a[t]:       # pivot broken -> new low
                state = 0; L = c[t]
            elif c[t] <= L + hold * a[t]:
                state = 2; L2 = c[t]
        elif state == 2:
            if c[t] < L - hold * a[t]:
                state = 0; L = c[t]
            elif c[t] < L2:
                L2 = c[t]
            elif c[t] >= L2 + conf * a[t]:
                sig[t] = True; state = 0; L = c[t]
    return sig


def event_study(T, S):
    o, c, a = T.O.to_numpy(), T.C.to_numpy(), T.A.to_numpy(); n = len(T)
    yrs = T.index.year.to_numpy()
    per = np.where(yrs <= 2017, "2009–17", np.where(yrs <= 2021, "2018–21", "2022–26"))
    rows = []
    for name, (s, side) in S.items():
        s = s.fillna(False).to_numpy().astype(bool)
        for h in HS:
            fwd = np.full(n, np.nan); fwd[:-h] = (c[h:] - o[1:n - h + 1]) / a[:-h]
            base = pd.Series(side * fwd).groupby(yrs).transform("mean").to_numpy()
            idx = np.flatnonzero(s & np.isfinite(fwd) & np.isfinite(a) & (yrs >= 2009))
            keep, last = [], -10**9
            for i in idx:
                if i - last >= h:
                    keep.append(i); last = i
            keep = np.array(keep, int)
            if len(keep) < 5:
                rows.append(dict(hypoteza=name, h=h, n=len(keep))); continue
            r = side * fwd[keep]; ex = r - base[keep]
            row = dict(hypoteza=name, h=h, n=len(keep), R=r.mean(), excess=ex.mean(),
                       t_excess=ex.mean() / ex.std(ddof=1) * np.sqrt(len(ex)), win=(r > 0).mean())
            for p in ("2009–17", "2018–21", "2022–26"):
                m = per[keep] == p
                row[f"ex {p}"] = ex[m].mean() if m.any() else np.nan; row[f"n {p}"] = int(m.sum())
            rows.append(row)
    return pd.DataFrame(rows)


def round_numbers():
    """H2 on raw (non back-adjusted) ES3000 daily data 2018-2026: first close above a new 100-point level"""
    p = "/tmp/claude-0/data/es1m_daily_raw.parquet"
    if not os.path.exists(p):
        return None
    D = pd.read_parquet(p)
    c = D["C"].astype(float).to_numpy(); o = D["O"].astype(float).to_numpy()
    rows = []
    for step, h in [(st, hh) for st in (100, 50) for hh in (5, 10, 20)]:
        lvl = np.floor(c / step); prevmax = np.maximum.accumulate(np.r_[lvl[0], lvl[:-1]])
        sig = lvl > prevmax
        fwd = np.full(len(c), np.nan); fwd[:-h] = (c[h:] / o[1:len(c) - h + 1] - 1) * 100
        base = np.nanmean(fwd)
        idx = np.flatnonzero(sig & np.isfinite(fwd))
        keep, last = [], -10**9
        for i in idx:
            if i - last >= h:
                keep.append(i); last = i
        r = fwd[keep]
        rows.append(dict(hypoteza=f"H2 první close nad novou úrovní po {step} bodech (2018–26, surové ceny)", h=h, n=len(r),
                         R_pct=r.mean(), prumer_dne_pct=base, excess_pct=r.mean() - base,
                         t_excess=(r - base).mean() / r.std(ddof=1) * np.sqrt(len(r)) if len(r) > 2 else np.nan))
    return pd.DataFrame(rows)


def systems(T, S):
    """H11: entries H1 / H3 / reference with Wyckoff exits (stop 1 ATR, target 3 ATR, max 10 days) vs 20-day hold"""
    o, h_, l, c, a = (T[k].to_numpy() for k in ("O", "H", "L", "C", "A")); n = len(T)
    es, _ = run_pos(T.rename(columns={"A": "ATRx"}), np.ones(n))
    rows = []
    for name in ("H1 průraz z konsolidace (20D rozsah ≤ 3 ATR)", "H3 nové maximum po normální reakci (≥1,5 ATR)",
                 "H7 test pivotu (dvojité dno)", "H9 panika: pokles ≥ 5 ATR + objem ≥ 1,5×", "Referenční: nové 20D maximum (bez podmínek)"):
        s = S[name][0].fillna(False).to_numpy()
        for ex_name, stop, tgt, maxd in (("Wyckoff: stop 1 ATR, cíl 3 ATR, max 10 dní", 1, 3, 10), ("držet 20 dní", None, None, 20)):
            pos = np.zeros(n); i = 0; trades = []
            while i < n - 1:
                if s[i] and np.isfinite(a[i]) and T.index[i].year >= 2009:
                    e = o[i + 1]; j = i + 1; px = None
                    while j < n and j <= i + maxd:
                        pos[j] = 1
                        if stop and l[j] <= e - stop * a[i]:
                            px = e - stop * a[i]; break
                        if tgt and h_[j] >= e + tgt * a[i]:
                            px = e + tgt * a[i]; break
                        j += 1
                    j = min(j, n - 1)
                    trades.append(((px if px is not None else c[j]) - e - 0.5) / a[i])
                    i = j + 1
                else:
                    i += 1
            tr = np.array(trades)
            r, _ = run_pos(T.rename(columns={"A": "ATRx"}), pos)
            pf = perf(r, es, "2009", "2026")
            rows.append(dict(vstup=name, vystup=ex_name, obchodu=len(tr), R_obchod=tr.mean() if len(tr) else np.nan,
                             t=tr.mean() / tr.std(ddof=1) * np.sqrt(len(tr)) if len(tr) > 2 else np.nan,
                             win=(tr > 0).mean() if len(tr) else np.nan, v_trhu=pos.mean(), CAGR=pf["CAGR"],
                             Sharpe=pf["Sharpe"], alfa_rok=pf["alfa_rok"], alfa_t=pf["alfa_t"]))
    bh = perf(es, es, "2009", "2026")
    rows.append(dict(vstup="Buy & hold ES", vystup="–", v_trhu=1.0, CAGR=bh["CAGR"], Sharpe=bh["Sharpe"]))
    return pd.DataFrame(rows)


def market_key_pct(T):
    """H13: Market Key with % thresholds (columns collapsed to trend state: up / down), long/flat"""
    c = T.C.to_numpy(); n = len(c)
    out = {}
    es, _ = run_pos(T.rename(columns={"A": "ATRx"}), np.ones(n))
    for thr in (0.05, 0.08, 0.10):
        pos = np.zeros(n); trend = 0; ext = c[0]; ph = np.nan; pl = np.nan; p = 0.0
        for t in range(1, n):
            if trend >= 0:
                if c[t] > ext:
                    ext = c[t]
                elif c[t] <= ext * (1 - thr):
                    ph = ext; trend = -1; ext = c[t]
            if trend < 0:
                if c[t] < ext:
                    ext = c[t]
                elif c[t] >= ext * (1 + thr):
                    pl = ext; trend = 1; ext = c[t]
            if np.isfinite(ph) and c[t] > ph * (1 + thr / 2):
                p = 1.0
            if np.isfinite(pl) and c[t] < pl * (1 - thr / 2):
                p = 0.0
            pos[t] = p
        r, _ = run_pos(T.rename(columns={"A": "ATRx"}), pos)
        pf = perf(r, es, "2009", "2026")
        out[f"Market Key {int(thr*100)} % (long/flat)"] = dict(v_trhu=pos[T.index.year >= 2009].mean(), **pf)
    out["Buy & hold ES"] = dict(v_trhu=1.0, **perf(es, es, "2009", "2026"))
    return pd.DataFrame(out).T


def main():
    T = load()
    S = signals(T)
    E = event_study(T, S)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200); pd.set_option("display.max_columns", 30)
    print(E.round(3).to_string())
    E.round(4).to_csv(os.path.join(OUT, "books_events.csv"), index=False)
    R2 = round_numbers()
    if R2 is not None:
        print(R2.round(3).to_string()); R2.round(4).to_csv(os.path.join(OUT, "books_round_numbers.csv"), index=False)
    else:
        print("H2: surová data nejsou k dispozici")
    Y = systems(T, S)
    print(Y.round(3).to_string()); Y.round(4).to_csv(os.path.join(OUT, "books_systems.csv"), index=False)
    M = market_key_pct(T)
    print(M.round(3).to_string()); M.round(4).to_csv(os.path.join(OUT, "books_market_key_pct.csv"))


if __name__ == "__main__":
    main()
