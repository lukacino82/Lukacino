"""Jesse Livermore's rules on ES daily data (2009-2026), fixed before testing.

Rules (How to Trade in Stocks 1940, Reminiscences 1923, as commonly summarised):
  P1 pivotal point     buy only when price breaks a pivotal point: a new N-day closing high (N = 20, 55, 252)
  P2 pyramiding        probe with 20 %, add 20 % at +1 ATR, 20 % at +2 ATR, 40 % at +3 ATR above the first entry
                       (adds only into profit, never average down)
  P3 cut losses        initial stop 2 ATR (variant: 10 % below entry, Livermore's maximum loss rule)
  P4 act right         time stop: not in profit after 10 days -> exit
  P5 sit tight         exit only on a "natural reaction" against the trend: close >= R ATR below the highest close
                       (R = 3 or 6), variant: close below the 20-day low
  P6 Market Key        zigzag pivots with threshold T ATR; long when the close exceeds the last pivot high by T/2,
                       exit (or short) when it falls below the last pivot low by T/2
Comparisons: the same rules without pyramiding (full size at entry), random entries with the same exits/pyramid
(200 runs), buy & hold. Execution at the next RTH open, cost 0.5 point per round turn per contract.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
OUT = os.path.join(HERE, "out")
PERIODS = (("2009–2017", "2009", "2017"), ("2018–2021", "2018", "2021"), ("2022–2026", "2022", "2026"),
           ("2009–2026", "2009", "2026"))


def load():
    import features as F
    T = F.load()["T"][["O", "H", "L", "C", "ATR"]].copy()
    T["ATR"] = T.ATR.shift()                       # known before the day
    return T.dropna()


def run_pos(T, target):
    """target position (0..1 or -1..1) decided at close t, executed at open t+1 -> daily returns"""
    o, c = T.O.to_numpy(), T.C.to_numpy()
    pos = np.r_[0.0, target[:-1]]                  # position held from open t
    prev = np.r_[0.0, pos[:-1]]
    r = np.zeros(len(T))
    r[1:] = prev[1:] * (o[1:] / c[:-1] - 1) + pos[1:] * (c[1:] / o[1:] - 1)
    r -= np.abs(pos - prev) * 0.25 / o              # 0.25 point per side
    return pd.Series(r, index=T.index), pd.Series(pos, index=T.index)


def breakout_system(T, N=55, pyramid=True, stop="atr2", trail=("atr", 3), time_stop=10, entries=None):
    """returns target position array and a trade list"""
    c, a = T.C.to_numpy(), T.ATR.to_numpy()
    hiN = pd.Series(c).shift().rolling(N).max().to_numpy()
    lo20 = pd.Series(c).shift().rolling(20).min().to_numpy()
    n = len(c); tgt = np.zeros(n); trades = []
    inpos = False; units = 0.0
    sig = (c > hiN) if entries is None else entries
    for t in range(n):
        if not inpos:
            if sig[t] and np.isfinite(a[t]):
                inpos = True; e = c[t]; ea = a[t]; peak = c[t]; t0 = t
                units = 0.2 if pyramid else 1.0
                stp = e - 2 * ea if stop == "atr2" else e * 0.9
        else:
            peak = max(peak, c[t])
            if pyramid:
                for k, add in ((1, 0.2), (2, 0.2), (3, 0.4)):
                    lvl = e + k * ea
                    need = {1: 0.4, 2: 0.6, 3: 1.0}[k]
                    if c[t] >= lvl and units < need - 1e-9:
                        units = need
            ex = c[t] <= stp
            if time_stop and t - t0 == time_stop and c[t] <= e:
                ex = True
            if trail[0] == "atr" and c[t] <= peak - trail[1] * a[t]:
                ex = True
            if trail[0] == "low20" and c[t] < lo20[t]:
                ex = True
            if ex:
                trades.append((T.index[t0], T.index[t], c[t] / e - 1, units, t - t0))
                inpos = False; units = 0.0
        tgt[t] = units if inpos else 0.0
    return tgt, trades


def market_key(T, thr=3.0, short=False):
    """zigzag with threshold thr*ATR on closes; long above last pivot high + thr/2 ATR, flat/short below
    last pivot low - thr/2 ATR"""
    c, a = T.C.to_numpy(), T.ATR.to_numpy()
    n = len(c); tgt = np.zeros(n)
    trend = 0; ext = c[0]; ph = np.nan; pl = np.nan; pos = 0.0
    for t in range(1, n):
        th = thr * a[t]
        if trend >= 0:
            if c[t] > ext:
                ext = c[t]
            elif ext - c[t] >= th:
                ph = ext; trend = -1; ext = c[t]
        if trend < 0:
            if c[t] < ext:
                ext = c[t]
            elif c[t] - ext >= th:
                pl = ext; trend = 1; ext = c[t]
        if np.isfinite(ph) and c[t] > ph + th / 2:
            pos = 1.0
        if np.isfinite(pl) and c[t] < pl - th / 2:
            pos = -1.0 if short else 0.0
        tgt[t] = pos
    return tgt


def perf(r, es, start, end):
    r = r.loc[start:end]; e = es.loc[start:end]
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    X = np.c_[np.ones(len(e)), e.to_numpy()]
    b, *_ = np.linalg.lstsq(X, r.to_numpy(), rcond=None)
    res = r.to_numpy() - X @ b
    se = np.sqrt(res.var(ddof=2) / len(r))
    return dict(CAGR=cagr, Sharpe=sh, maxDD=dd, beta=b[1], alfa_rok=b[0] * 252, alfa_t=b[0] / se)


def trade_stats(trades):
    if not trades:
        return {}
    d = pd.DataFrame(trades, columns=["in", "out", "ret", "units", "days"])
    w = d[d.ret > 0]; l = d[d.ret <= 0]
    top = d.ret.sort_values(ascending=False)
    share_top = top.head(max(1, len(d) // 10)).clip(lower=0).sum() / d.ret.clip(lower=0).sum() if (d.ret > 0).any() else np.nan
    return dict(obchodu=len(d), win=len(w) / len(d), prum_zisk=w.ret.mean(), prum_ztrata=l.ret.mean(),
                payoff=(w.ret.mean() / -l.ret.mean()) if len(l) and len(w) else np.nan, drzeni_dni=d.days.mean(),
                plna_pyramida=(d.units >= 0.999).mean(), podil_zisku_top10=share_top)


def main():
    os.makedirs(OUT, exist_ok=True)
    T = load()
    es, _ = run_pos(T, np.ones(len(T)))
    rows = []
    variants = []
    for N in (20, 55, 252):
        for pyr in (True, False):
            for stop in ("atr2", "pct10"):
                for trail in (("atr", 3), ("atr", 6), ("low20", 0)):
                    variants.append(("breakout", dict(N=N, pyramid=pyr, stop=stop, trail=trail)))
    for thr in (2.0, 3.0, 4.0):
        for sh in (False, True):
            variants.append(("marketkey", dict(thr=thr, short=sh)))
    store = {}
    for kind, p in variants:
        if kind == "breakout":
            tgt, tr = breakout_system(T, **p)
            name = f"Průraz {p['N']}D · {'pyramida' if p['pyramid'] else 'plná pozice'} · stop {'2 ATR' if p['stop']=='atr2' else '10 %'} · výstup {'reakce '+str(p['trail'][1])+' ATR' if p['trail'][0]=='atr' else '20denní low'}"
        else:
            tgt = market_key(T, **p); tr = []
            name = f"Market Key {p['thr']:.0f} ATR · {'long/short' if p['short'] else 'long/flat'}"
        r, pos = run_pos(T, tgt)
        store[name] = (r, pos, tgt, tr, kind, p)
        row = dict(system=name, expozice=pos.abs().mean())
        for pn, s, e in PERIODS:
            pf = perf(r, es, s, e)
            for k, v in pf.items():
                row[f"{k} {pn}"] = v
        row.update(trade_stats(tr))
        rows.append(row)
    bh = dict(system="Buy & hold ES", expozice=1.0)
    for pn, s, e in PERIODS:
        for k, v in perf(es, es, s, e).items():
            bh[f"{k} {pn}"] = v
    S = pd.DataFrame([bh] + rows)
    S.round(4).to_csv(os.path.join(OUT, "livermore_all.csv"), index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 50); pd.set_option("display.max_rows", 100)
    cols = ["system", "expozice", "CAGR 2009–2026", "Sharpe 2009–2026", "maxDD 2009–2026", "alfa_rok 2009–2026",
            "alfa_t 2009–2026", "alfa_t 2009–2017", "alfa_t 2018–2021", "alfa_t 2022–2026", "obchodu", "win",
            "payoff", "podil_zisku_top10", "plna_pyramida"]
    print(S[cols].round(3).to_string())
    # null: random entries with the same pyramid/exit rules (for the main breakout config)
    rng = np.random.default_rng(7)
    main_cfg = dict(N=55, pyramid=True, stop="atr2", trail=("atr", 3))
    base_tgt, base_tr = breakout_system(T, **main_cfg)
    br, _ = run_pos(T, base_tgt)
    real = perf(br, es, "2009", "2026")
    n_sig = len(base_tr)
    nulls = []
    for i in range(200):
        ent = np.zeros(len(T), bool)
        ent[rng.choice(np.arange(260, len(T)), size=n_sig * 3, replace=False)] = True
        tg, trr = breakout_system(T, entries=ent, **{k: v for k, v in main_cfg.items() if k != "N"}, N=55)
        rr, _ = run_pos(T, tg)
        nulls.append(perf(rr, es, "2009", "2026"))
    Nn = pd.DataFrame(nulls)
    null_res = dict(real_alfa=real["alfa_rok"], real_sharpe=real["Sharpe"],
                    null_alfa_mean=Nn.alfa_rok.mean(), null_alfa_p95=Nn.alfa_rok.quantile(0.95),
                    p_alfa=(Nn.alfa_rok >= real["alfa_rok"]).mean(), null_sharpe_mean=Nn.Sharpe.mean(),
                    p_sharpe=(Nn.Sharpe >= real["Sharpe"]).mean())
    print("null (náhodné vstupy, stejná pyramida a výstupy):", {k: round(v, 3) for k, v in null_res.items()})
    # yearly for the main configs
    pick = ["Průraz 55D · pyramida · stop 2 ATR · výstup reakce 3 ATR", "Průraz 55D · plná pozice · stop 2 ATR · výstup reakce 3 ATR",
            "Průraz 252D · pyramida · stop 10 % · výstup reakce 6 ATR", "Market Key 3 ATR · long/flat", "Market Key 3 ATR · long/short"]
    Y = pd.DataFrame({k: (1 + store[k][0]).groupby(T.index.year).prod() - 1 for k in pick})
    Y["Buy & hold ES"] = (1 + es).groupby(T.index.year).prod() - 1
    Y = (Y.loc[2009:] * 100).round(1)
    print(Y.to_string())
    Y.to_csv(os.path.join(OUT, "livermore_years.csv"))
    eq = {k: ((1 + store[k][0].loc["2009":]).cumprod()).iloc[::5].round(4).tolist() for k in pick}
    eq["Buy & hold ES"] = ((1 + es.loc["2009":]).cumprod()).iloc[::5].round(4).tolist()
    json.dump(dict(null=null_res, dates=[str(d)[:10] for d in es.loc["2009":].index[::5]], eq=eq),
              open(os.path.join(OUT, "livermore.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
