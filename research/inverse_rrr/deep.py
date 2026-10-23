"""Plateau tests for the two signals that survived honest selection:

A  SHORT at 10:00 / 10:30 after the previous 60 minutes fell >= x (ATR-50 units), exit TP/SL or RTH close.
   Found by DISC-only selection (2008-17) - VAL and OOS were never looked at when picking it.
B  LONG at 09:00 after the 08:00-09:00 drop >= x points (8:30 macro data), small TP, wide SL.
   Found on the whole sample (robust filter), so it needs the neighbourhood check to be believed.

For each family a neighbourhood grid (x, slot, TP, SL) is evaluated per period. A real effect shows as a
plateau (most neighbours positive in OOS), a fluke as one isolated point.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from irr_engine import TPS, SLS, COST  # noqa: E402
from playbook import load, label, PER, INT, bh_points  # noqa: E402

DATA = "/tmp/claude-0/data"
OUT = os.path.join(HERE, "out")


def pnl(Zs, side, tp, sl, scale):
    it = int(np.flatnonzero(TPS == tp)[0]); js = int(np.flatnonzero(SLS == sl)[0])
    a = Zs[f"tp_{side}_eod"][:, it]; b = Zs[f"sl_{side}_eod"][:, js]; cp = Zs[f"cp_{side}_eod"]
    win = a < b; loss = (b <= a) & (b < INT)
    return np.where(win, tp * scale, np.where(loss, -sl * scale, cp)) - COST, np.where(win, 1, np.where(loss, -1, 0))


def grid(E, Zs, scale, side, times, xs, pairs, scaled_move):
    mv = E.m60.to_numpy() / (scale if scaled_move else 1.0)
    rows = []
    for t in times:
        for x in xs:
            m0 = (E.time == t).to_numpy() & (mv <= -x)
            for tp, sl in pairs:
                p, c = pnl(Zs, side, tp, sl, scale)
                base = (E.time == t).to_numpy()
                r = dict(time=t, x=x, tp=tp, sl=sl)
                for per in PER:
                    mp = m0 & (E.per == per).to_numpy(); bp = base & (E.per == per).to_numpy()
                    x_ = p[mp]
                    r[f"n_{per}"] = int(mp.sum()); r[f"exp_{per}"] = x_.mean() if len(x_) else np.nan
                    r[f"t_{per}"] = x_.mean() / (x_.std(ddof=1) / np.sqrt(len(x_))) if len(x_) > 2 and x_.std() > 0 else np.nan
                    r[f"edge_{per}"] = r[f"exp_{per}"] - p[bp].mean()
                rows.append(r)
    return pd.DataFrame(rows)


def one(E, Zs, scale, side, t, x, tp, sl, scaled_move, bh_year):
    mv = E.m60.to_numpy() / (scale if scaled_move else 1.0)
    m = (E.time == t).to_numpy() & (mv <= -x)
    p, c = pnl(Zs, side, tp, sl, scale)
    D = pd.DataFrame({"gday": E.gday[m].to_numpy(), "year": E.year[m].to_numpy(), "dow": E.dow[m].to_numpy(),
                      "month": E.month[m].to_numpy(), "per": E.per[m].to_numpy(), "p": p[m], "c": c[m], "atr": E.atr[m].to_numpy()})
    Y = D.groupby("year").agg(obchodu=("p", "size"), body=("p", "sum"), exp=("p", "mean"), win=("c", lambda v: (v == 1).mean()))
    Y["B&H body"] = bh_year.reindex(Y.index).to_numpy()
    return D, Y


def main():
    E, Zp = load()
    Za = dict(np.load(os.path.join(DATA, "irr_atr50.npz")))
    sc = E.atr.to_numpy() / 50.0
    bh_year, C = bh_points()
    # ---------------- A: short after opening drop (ATR units)
    pairsA = [(tp, sl) for tp in (12, 15, 20, 25) for sl in (15, 20, 25, 30)]
    A = grid(E, Za, sc, "S", ["09:30", "10:00", "10:30", "11:00"], [5, 10, 15, 20], pairsA, True)
    A.round(3).to_csv(os.path.join(OUT, "plateau_short_open_drop.csv"), index=False)
    # same thing in plain points
    Ap = grid(E, Zp, np.ones(len(E)), "S", ["10:00", "10:30"], [10, 15, 20], [(15, 15), (20, 20), (25, 25), (20, 30)], False)
    Ap.round(3).to_csv(os.path.join(OUT, "plateau_short_open_drop_pts.csv"), index=False)
    # mirror: long after opening rally (is it symmetric momentum?)
    E2 = E.copy(); E2["m60"] = -E2.m60
    Am = grid(E2, Za, sc, "L", ["10:00", "10:30"], [5, 10, 15, 20], [(15, 20), (20, 20), (25, 25)], True)
    Am.round(3).to_csv(os.path.join(OUT, "plateau_long_open_rally.csv"), index=False)
    # ---------------- B: long 09:00 after pre-open drop (points)
    pairsB = [(6, 20), (6, 30), (8, 30), (10, 30), (6, 40), (10, 50), (12, 40), (15, 15), (15, 50)]
    B = grid(E, Zp, np.ones(len(E)), "L", ["08:00", "08:30", "09:00", "09:30"], [5, 10, 15, 20], pairsB, False)
    B.round(3).to_csv(os.path.join(OUT, "plateau_long_preopen_drop.csv"), index=False)
    Ba = grid(E, Za, sc, "L", ["09:00"], [5, 10, 15, 20], pairsB, True)
    Ba.round(3).to_csv(os.path.join(OUT, "plateau_long_preopen_drop_atr.csv"), index=False)

    def share(df, col="exp_OOS"):
        d = df[df.n_OOS >= 20]
        return dict(n=len(d), pos_OOS=float((d[col] > 0).mean()), pos_VAL=float((d.exp_VAL > 0).mean()),
                    pos_DISC=float((d.exp_DISC > 0).mean()), edge_pos_OOS=float((d.edge_OOS > 0).mean()),
                    median_exp_OOS=float(d[col].median()))
    plate = {"A short po propadu (ATR)": share(A), "A short po propadu (body)": share(Ap),
             "A zrcadlo: long po růstu": share(Am), "B long 09:00 po poklesu (body)": share(B[B.time == "09:00"]),
             "B okolí 08:00/08:30/09:30": share(B[B.time != "09:00"]), "B long 09:00 (ATR)": share(Ba)}
    pd.set_option("display.width", 250)
    for k, v in plate.items():
        print(k, {a: round(b, 3) for a, b in v.items()})
    print(A[(A.time == "10:00")].round(2).to_string())
    print(B[B.time == "09:00"].round(2).to_string())
    print(Am.round(2).to_string())
    # ---------------- final picks: equity, years, dow
    picks = {
        "A: short 10:00 po propadu ≥0,3 ATR · TP/SL 0,4 ATR": (Za, sc, "S", "10:00", 15, 20, 20, True),
        "B: long 09:00 po poklesu ≥10 b. · TP 6 / SL 30": (Zp, np.ones(len(E)), "L", "09:00", 10, 6, 30, False),
    }
    res = {}
    for name, (Zs, s, side, t, x, tp, sl, smv) in picks.items():
        D, Y = one(E, Zs, s, side, t, x, tp, sl, smv, bh_year)
        Y.round(2).to_csv(os.path.join(OUT, f"pick_{name[0]}_yearly.csv"))
        print(name); print(Y.round(2).to_string())
        eq = D.p.cumsum()
        dd = (eq - eq.cummax().clip(lower=0)).min()
        print("dow", D.groupby("dow").p.mean().round(2).to_dict(), "maxDD", round(dd, 1), "n", len(D),
              "SL", int((D.c == -1).sum()), "win", round((D.c == 1).mean(), 3))
        res[name] = dict(d=[str(x)[:10] for x in D.gday], e=np.round(eq.to_numpy(), 1).tolist(),
                         yearly=json.loads(Y.round(2).reset_index().to_json(orient="records")),
                         dow=D.groupby("dow").p.mean().round(2).tolist(), month=D.groupby("month").p.mean().round(2).to_dict(),
                         n=len(D), sl_hits=int((D.c == -1).sum()), win=float((D.c == 1).mean()), maxdd=float(dd),
                         exp={p: float(D.p[D.per == p].mean()) for p in PER}, nper={p: int((D.per == p).sum()) for p in PER},
                         atr_med_oos=float(D.atr[D.per == "OOS"].median()))
    data = json.load(open(os.path.join(OUT, "report_data.json")))
    data["plateau"] = plate
    data["picks"] = res
    data["plateauA"] = json.loads(A.round(3).to_json(orient="records"))
    data["plateauB"] = json.loads(B.round(3).to_json(orient="records"))
    data["mirror"] = json.loads(Am.round(3).to_json(orient="records"))
    json.dump(data, open(os.path.join(OUT, "report_data.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
