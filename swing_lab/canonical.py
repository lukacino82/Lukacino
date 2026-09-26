"""
Canonical published swing systems - PRE-REGISTERED, parameters exactly as published, nothing
tuned on this data. For these rules the whole ES sample 2016-2026 is genuine out-of-sample,
because the parameters were fixed by their authors years before.

Every rule: signal at RTH close, fill at that close (MOC), 0.5 pt round-trip cost, 1 ES.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab import Lab

INF = np.inf


def canonical(d: pd.DataFrame):
    c = d.close
    up = c > d.sma200
    x = lambda cond: np.asarray(cond, bool).astype(np.int8)  # noqa: E731
    systems = {
        # Connors & Alvarez, "Short Term Trading Strategies That Work" (2008)
        "C1 Connors RSI(2)<10 >SMA200, exit C>SMA5":
            dict(side=x(up & (d.rsi2 < 10)), xsig=x(c > d.sma5)),
        # Connors & Alvarez, "High Probability ETF Trading" (2009): cumulative RSI
        "C2 Cum.RSI(2) 2d<35 >SMA200, exit RSI2>65":
            dict(side=x(up & (d.crsi2_2 < 35)), xsig=x(d.rsi2 > 65)),
        # Connors & Alvarez (2009): Double 7s
        "C3 Double 7s >SMA200, exit 7d high close":
            dict(side=x(up & d.ll7), xsig=x(d.hh7)),
        # Connors & Alvarez (2009): multiple days down
        "C4 4 down closes >SMA200, exit C>SMA5":
            dict(side=x(up & (d.downdays >= 4)), xsig=x(c > d.sma5)),
        # Connors & Alvarez (2009): %b
        "C5 %b<0.2 3 days >SMA200, exit %b>0.8":
            dict(side=x(up & (d.bb_pctb < 0.2) & (d.bb_pctb.shift() < 0.2) & (d.bb_pctb.shift(2) < 0.2)),
                 xsig=x(d.bb_pctb > 0.8)),
        # IBS mean reversion (Pagonidis 2013 / widely published): IBS<0.2, exit close > prior high
        "C6 IBS<0.2, exit C>prev high":
            dict(side=x(d.ibs < 0.2), xsig=x(c > d.high.shift())),
        # Turnaround Tuesday (L. Williams / Toby Crabel era lore): down Monday -> hold one day
        "C7 Turnaround Monday->Tuesday":
            dict(side=x((d.dow == 0) & (d.ret < 0)), max_days=1),
        # Turn of month (Ariel 1987; Lakonishok & Smidt 1988; McConnell & Xu 2008): last day .. 3rd day
        "C8 Turn-of-month (d-1 .. +3)":
            dict(side=x(d.tdm_rev == 2), max_days=4),
        # Pre-holiday effect (Ariel 1990)
        "C9 Pre-holiday day":
            dict(side=x(pd.Series(d.pre_holiday.values, index=d.index).shift(-1).fillna(False).astype(bool)),
                 max_days=1),
        # Faber (2007) trend filter as a B&H replacement: long while close > 200-day SMA
        "T1 Faber trend: long while C>SMA200":
            dict(side=x(up), xsig=x(~up)),
    }
    return systems


def run_all(lab: Lab, cost=0.5):
    out, pnls, trades = {}, {}, {}
    for name, cfg in canonical(lab.d).items():
        cfg = dict(cfg, cost=cost)
        pnl, pos, tdf = lab.run(cfg, full=True)
        st = lab.stats(pnl, pos, tdf)
        st["hold"] = float(tdf.bars.mean()) if len(tdf) else 0
        out[name] = st
        pnls[name] = pnl
        trades[name] = tdf
    return pd.DataFrame(out).T, pd.DataFrame(pnls, index=lab.idx), trades


if __name__ == "__main__":
    lab = Lab()
    st, pnl, _ = run_all(lab)
    pd.set_option("display.width", 250)
    cols = ["trades", "win", "avg", "pf", "total", "mdd", "sharpe", "mar", "alpha_ann", "alpha_t", "beta", "exposure",
            "disc_ann", "val_ann", "oos_ann", "years_pos"]
    print(st[cols].astype(float).round(2).to_string())
    print("B&H", {k: round(float(lab.bh_stats[k]), 2) for k in ["total", "mdd", "sharpe", "mar", "disc_ann", "val_ann", "oos_ann"]})
    st15, _, _ = run_all(lab, cost=1.5)
    print("cost 1.5 avg:", st15.avg.astype(float).round(2).to_dict())
