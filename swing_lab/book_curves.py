"""
Equity curves of exactly what the Sierra study trades: the 48 presets in swing_presets.csv,
grouped into their 12 families, plus the whole book, against buy & hold.

Sizing mirrors the live plan: 1 MES per preset. One family = 4 presets = 0.4 ES equivalent,
the whole book = 4.8 ES at full exposure, 0.95 ES on average.
Costs: 0.7 points per MES round trip (about 0.25 spread + 0.4 commission), higher than the
0.5 used in the ES research, because a MES commission is the same in dollars but the point
is worth a tenth as much.

Returns are shown on a fixed 1-ES notional so the book and buy & hold are directly comparable.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import systems as S
from lab import Lab
from sieve import RES

COST_MES = 0.7
MES_PER_ES = 0.1
LABEL = {
    "LMT_RSI#<#_#ATR": "Limitní nákup pod close po oversold RSI",
    "C<dvwap#sd": "Close pod denním VWAP − kσ",
    "C<wvwap#sd": "Close pod týdenním VWAP − kσ",
    "C06": "Reclaim krátké MA po drawdownu",
    "P_Hi#DD>#&RSI#<#": "Drawdown od 20/50d high + RSI(2)",
    "IBS<#": "IBS, close u denního low",
    "WR#<#": "Williams %R extrém",
    "D01": "VWAP pásmo a reclaim",
    "CloseAt#dLow": "Close na N-denním minimu",
    "RSI#<#": "RSI(2–5) oversold",
    "P_Hi#DD>#&IBS<#": "Drawdown od high + IBS",
    "ConnorsRSI<#": "Connors RSI extrém",
}


def stats(r, bench):
    eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (252 / len(r)) - 1
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0
    beta = np.cov(r, bench)[0, 1] / bench.var()
    res = r - beta * bench
    ir = res.mean() / res.std() * np.sqrt(252) if res.std() > 0 else 0.0
    return dict(cagr=round(cagr * 100, 2), maxdd=round(dd * 100, 1), vol=round(r.std() * np.sqrt(252) * 100, 1),
                sharpe=round(sh, 2), mar=round(cagr / -dd, 2) if dd < 0 else 0.0,
                beta=round(beta, 2), alpha_t=round(ir * np.sqrt(len(r) / 252), 2))


def main():
    lab = Lab()
    s0 = lab.start_i
    close = lab.d.close.values
    prev = np.r_[np.nan, close[:-1]]
    idx = lab.idx[s0:]
    pre = pd.read_csv(RES / "swing_presets.csv")
    setups = {s[0]: s for s in S.setups(lab.d)}
    exits = {e[0]: e for e in S.exits(lab.d)}
    reg = S.regimes(lab.d)

    pnl, pos, ntr = {}, {}, {}
    for r in pre.itertuples():
        cfg = S.build_cfg(lab.d, setups[r.setup], exits[r.exit], 1, reg[r.regime], COST_MES)
        p, ps, tr = lab.run(cfg)
        pnl[r.id] = p * MES_PER_ES          # 1 MES
        pos[r.id] = np.abs(ps) * MES_PER_ES
        ntr[r.id] = len(tr[0])

    fams = pre.groupby("family").id.apply(list).to_dict()
    ret = lambda p: (p / prev)[s0:]          # noqa: E731  return on a fixed 1-ES notional
    bh = ret(lab.bh)

    rows, curves = [], {"dates": [str(x.date()) for x in idx]}
    for f, ids in fams.items():
        p = sum(pnl[i] for i in ids)
        expo = sum(pos[i] for i in ids)
        r = ret(p)
        st = stats(r, bh)
        st.update(family=LABEL.get(f, f), key=f, presets=len(ids), trades=sum(ntr[i] for i in ids),
                  total_pts=round(float(p[s0:].sum()), 0), avg_expo=round(float(expo[s0:].mean()), 2))
        rows.append(st)
        curves[LABEL.get(f, f)] = list(np.round((np.cumprod(1 + r) - 1) * 100, 3))
    book = sum(pnl.values())
    book_expo = sum(pos.values())
    rb = ret(book)
    curves["Celá kniha (48 presetů)"] = list(np.round((np.cumprod(1 + rb) - 1) * 100, 3))
    curves["Buy & Hold 1 ES"] = list(np.round((np.cumprod(1 + bh) - 1) * 100, 3))
    curves["B&H + kniha"] = list(np.round((np.cumprod(1 + bh + rb) - 1) * 100, 3))
    # volatility-matched book: same annual volatility as buy & hold
    k = bh.std() / rb.std()
    curves[f"Kniha škálovaná na riziko B&H ({k:.1f}x)"] = list(np.round((np.cumprod(1 + rb * k) - 1) * 100, 3))

    df = pd.DataFrame(rows).sort_values("total_pts", ascending=False)
    books = {
        "Buy & Hold 1 ES": stats(bh, bh),
        "Celá kniha (48 presetů, 1 MES každý)": stats(rb, bh),
        f"Kniha škálovaná na riziko B&H ({k:.1f}x)": stats(rb * k, bh),
        "B&H + kniha": stats(bh + rb, bh),
    }
    books["Celá kniha (48 presetů, 1 MES každý)"].update(
        total_pts=round(float(book[s0:].sum())), avg_expo=round(float(book_expo[s0:].mean()), 2),
        max_expo=round(float(book_expo[s0:].max()), 1), trades=int(sum(ntr.values())))
    books["Buy & Hold 1 ES"]["total_pts"] = round(float(lab.bh[s0:].sum()))

    yrs = idx.year.values
    yearly = pd.DataFrame({"Buy & Hold": pd.Series(bh).groupby(yrs).sum() * 100,
                           "Kniha": pd.Series(rb).groupby(yrs).sum() * 100,
                           "B&H + kniha": pd.Series(bh + rb).groupby(yrs).sum() * 100}).round(1)

    out = dict(curves=curves, families=df.to_dict("records"),
               books={k_: v for k_, v in books.items()},
               yearly=yearly.reset_index().rename(columns={"index": "year"}).to_dict("records"),
               cost=COST_MES, vol_mult=round(float(k), 2),
               period=[str(idx[0].date()), str(idx[-1].date())])
    json.dump(out, open(RES / "book_curves.json", "w"), default=float)
    pd.set_option("display.width", 250)
    print(df[["family", "presets", "trades", "total_pts", "avg_expo", "cagr", "maxdd", "sharpe", "mar", "beta", "alpha_t"]].to_string(index=False))
    print()
    print(pd.DataFrame(books).T.to_string())
    print()
    print(yearly.to_string())


if __name__ == "__main__":
    main()
