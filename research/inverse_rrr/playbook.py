"""Honest evaluation of the inverse-RRR grid (long focus) and per-entry deep dives.

1. Selection on DISC only (2008-2017) with a 'black swan' penalty: every combo gets one extra full SL loss
   added to its sample, so t-stats of 100 % win-rate combos are finite. The DISC top lists are then judged
   only on VAL (2018-21) and OOS (2022-26).
2. Hour map: probability that a long entry at a given slot reaches +TP before the RTH close (MFE), and that
   it reaches -TP first (MAE), per period; typical drawdown before the TP is hit.
3. TP x SL heatmap of random long entries: expectancy vs random-walk win rate (inverse RRR does not make edge).
4. Fixed candidates -> one trade per day (eod horizon never overlaps), yearly points vs buy & hold points,
   day of week, month, SL-hit frequency, longest run without an SL, max drawdown.
Outputs: out/*.csv and out/report_data.json (for the HTML report).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "swing_alpha"))
from irr_engine import TPS, SLS, COST  # noqa: E402
from irr_analysis import rule_masks, period  # noqa: E402

DATA = "/tmp/claude-0/data"
OUT = os.path.join(HERE, "out")
INT = 2**31 - 1
PER = ("DISC", "VAL", "OOS")


def label(m):
    t = 18 * 60 + int(m); return f"{t // 60 % 24:02d}:{t % 60:02d}"


def tstat(n, s, s2, infl):
    m = s / n; v = (s2 / n - m ** 2) * n / np.maximum(n - 1, 1)
    return m, m / np.sqrt(np.maximum(v, 1e-12) / n) / infl


# ---------------------------------------------------------------- 1. DISC-only selection with black-swan penalty
def selection():
    G = pd.read_parquet(os.path.join(DATA, "irr_grid.parquet"))
    keys = ["scale", "side", "hz", "rule", "slot", "tp", "sl"]
    W = G.pivot_table(index=keys, columns="p", values=["n", "s", "s2"], aggfunc="sum").fillna(0)
    W.columns = [f"{a}_{b}" for a, b in W.columns]
    W = W.reset_index()
    infl = np.where(W.hz == "end5", np.sqrt(5), 1.0)
    loss = W.sl + COST            # points scale: one full SL loss (atr50 rows: SL x ATR/50 ~ SL, good enough)
    for p in PER:
        n = W[f"n_{p}"]; s = W[f"s_{p}"]; s2 = W[f"s2_{p}"]
        W[f"exp_{p}"] = s / n.replace(0, np.nan)
        _, W[f"tpen_{p}"] = tstat(n + 1, s - loss, s2 + loss ** 2, infl)   # +1 black swan
    base = W[W.rule == "BASE"].set_index(["scale", "side", "hz", "slot", "tp", "sl"])
    k = pd.MultiIndex.from_frame(W[["scale", "side", "hz", "slot", "tp", "sl"]])
    for p in PER:
        W[f"edge_{p}"] = W[f"exp_{p}"] - base[f"exp_{p}"].reindex(k).to_numpy()
    W["time"] = W.slot.map(label)
    W["rw_win"] = W.sl / (W.tp + W.sl)
    rows = []
    cand = W[(W.rule != "BASE") & (W.n_DISC >= 100) & (W.n_VAL >= 30) & (W.n_OOS >= 30)]
    groups = {
        "vše (long+short, eod+5d, body+ATR)": cand,
        "long, do close (eod), body": cand[(cand.side == "L") & (cand.hz == "eod") & (cand.scale == "pts")],
        "long eod, TP 12–25 b.": cand[(cand.side == "L") & (cand.hz == "eod") & (cand.scale == "pts") & (cand.tp >= 12)],
        "long eod, RRR 1:1": cand[(cand.side == "L") & (cand.hz == "eod") & (cand.tp == cand.sl)],
        "long eod, obrácené RRR (SL ≥ 3×TP)": cand[(cand.side == "L") & (cand.hz == "eod") & (cand.sl >= 3 * cand.tp)],
        "short (vše)": cand[cand.side == "S"],
    }
    tops = {}
    for name, C in groups.items():
        for top in (20, 100):
            T = C.sort_values("tpen_DISC", ascending=False).head(top)
            rows.append(dict(skupina=name, top=top, kombinaci=len(C), t_DISC_median=T.tpen_DISC.median(),
                             exp_DISC=T.exp_DISC.mean(), exp_VAL=T.exp_VAL.mean(), exp_OOS=T.exp_OOS.mean(),
                             edge_DISC=T.edge_DISC.mean(), edge_VAL=T.edge_VAL.mean(), edge_OOS=T.edge_OOS.mean(),
                             podil_OOS_exp_kladne=(T.exp_OOS > 0).mean(), podil_OOS_edge_kladne=(T.edge_OOS > 0).mean(),
                             podil_OOS_t2=(T.tpen_OOS >= 2).mean()))
        tops[name] = C.sort_values("tpen_DISC", ascending=False).head(15)
    S = pd.DataFrame(rows)
    # reference: share of ALL candidate combos with positive OOS edge (what a random pick gives)
    ref = dict(vse_OOS_edge_kladne=float((cand.edge_OOS > 0).mean()), vse_OOS_exp_kladne=float((cand.exp_OOS > 0).mean()),
               long_eod_OOS_edge_kladne=float((groups["long, do close (eod), body"].edge_OOS > 0).mean()))
    S.round(3).to_csv(os.path.join(OUT, "selection_disc_only.csv"), index=False)
    cols = ["scale", "side", "hz", "rule", "time", "tp", "sl", "n_DISC", "n_OOS", "tpen_DISC", "exp_DISC", "exp_VAL", "exp_OOS",
            "edge_DISC", "edge_VAL", "edge_OOS", "rw_win"]
    T = pd.concat([v.assign(skupina=k) for k, v in tops.items()])[["skupina"] + cols]
    T.round(3).to_csv(os.path.join(OUT, "selection_top15.csv"), index=False)
    return S, T, ref


# ---------------------------------------------------------------- per-entry helpers
def load():
    E = pd.read_parquet(os.path.join(DATA, "irr_entries.parquet"))
    E["per"] = period(E.year.to_numpy())
    E["time"] = E.slot.map(label)
    E["month"] = pd.to_datetime(E.gday).dt.month
    Z = dict(np.load(os.path.join(DATA, "irr_pts.npz")))
    return E, Z


def pnl_of(Z, side, hz, tp, sl):
    it = int(np.flatnonzero(TPS == tp)[0]); js = int(np.flatnonzero(SLS == sl)[0])
    a = Z[f"tp_{side}_{hz}"][:, it]; b = Z[f"sl_{side}_{hz}"][:, js]; cp = Z[f"cp_{side}_{hz}"]
    win = a < b; loss = (b <= a) & (b < INT)
    code = np.where(win, 1, np.where(loss, -1, 0))
    return np.where(win, tp, np.where(loss, -sl, cp)) - COST, code


# ---------------------------------------------------------------- 2. hour map
def hour_map(E, Z):
    rows = []
    for tp in (10, 12, 15, 20, 25):
        it = int(np.flatnonzero(TPS == tp)[0]); js = int(np.flatnonzero(SLS == tp)[0])
        up = Z["tp_L_eod"][:, it] < INT          # long reaches +tp before RTH close
        dn = Z["sl_L_eod"][:, js] < INT          # reaches -tp before RTH close
        upfirst = Z["tp_L_eod"][:, it] < Z["sl_L_eod"][:, js]
        df = pd.DataFrame({"time": E.time, "per": E.per, "up": up, "dn": dn, "upfirst": upfirst, "slot": E.slot})
        for (t, p), g in df.groupby(["time", "per"]):
            rows.append(dict(tp=tp, time=t, slot=g.slot.iloc[0], per=p, n=len(g), p_up=g.up.mean(), p_dn=g.dn.mean(),
                             p_up_first=g.upfirst.mean()))
        for t, g in df.groupby("time"):
            rows.append(dict(tp=tp, time=t, slot=g.slot.iloc[0], per="ALL", n=len(g), p_up=g.up.mean(), p_dn=g.dn.mean(),
                             p_up_first=g.upfirst.mean()))
    H = pd.DataFrame(rows).sort_values(["tp", "per", "slot"])
    H.round(4).to_csv(os.path.join(OUT, "hour_map.csv"), index=False)
    # same in ATR-50 units (15 points in 2009 is a different thing than in 2025)
    Za = np.load(os.path.join(DATA, "irr_atr50.npz"))
    it = int(np.flatnonzero(TPS == 15)[0]); js = int(np.flatnonzero(SLS == 15)[0])
    up = Za["tp_L_eod"][:, it] < INT; dn = Za["sl_L_eod"][:, js] < INT
    Ha = pd.DataFrame({"time": E.time, "slot": E.slot, "per": E.per, "up": up, "dn": dn}).groupby(["slot", "time", "per"]).mean()
    Ha = Ha.reset_index().round(4); Ha.to_csv(os.path.join(OUT, "hour_map_atr15.csv"), index=False)
    # per-year probability of +15 before the close at selected slots (shows the price-level effect)
    it15 = int(np.flatnonzero(TPS == 15)[0])
    up15 = Z["tp_L_eod"][:, it15] < INT
    Y = pd.DataFrame({"year": E.year, "time": E.time, "up": up15, "atr": E.atr})
    Y = Y[Y.time.isin(["03:00", "08:00", "09:30", "10:00", "12:00", "14:00"])]
    YY = Y.pivot_table(index="year", columns="time", values="up", aggfunc="mean").round(3)
    YY["ATR_median"] = Y.groupby("year").atr.median().round(1)
    YY.to_csv(os.path.join(OUT, "p15_by_year.csv"))
    return H, Ha, YY


def mae_before_tp(E, Z, tp=15):
    """for long entries that hit +tp before the close: largest SL level already touched before the TP."""
    it = int(np.flatnonzero(TPS == tp)[0])
    a = Z["tp_L_eod"][:, it]; B = Z["sl_L_eod"]
    hit = a < INT
    touched = (B[hit] < a[hit, None])                      # [n, 14] adverse level touched before TP
    lvl = np.where(touched.any(1), SLS[np.where(touched, np.arange(len(SLS)), -1).max(1)], 0.0)
    df = pd.DataFrame({"time": E.time[hit].to_numpy(), "slot": E.slot[hit].to_numpy(), "mae": lvl})
    rows = []
    for (s, t), g in df.groupby(["slot", "time"]):
        r = dict(slot=s, time=t, n=len(g))
        for q in (0.5, 0.75, 0.9):
            r[f"q{int(q * 100)}"] = float(np.quantile(g.mae, q))
        for x in (4, 10, 20):
            r[f"p_mae_ge_{x}"] = float((g.mae >= x).mean())
        rows.append(r)
    M = pd.DataFrame(rows).sort_values("slot")
    M.round(3).to_csv(os.path.join(OUT, "mae_before_tp15.csv"), index=False)
    return M


# ---------------------------------------------------------------- 3. TP x SL heatmap (random long entry)
def heatmap(E, Z, times=("09:30",), hz="eod"):
    rows = []
    sel = E.time.isin(times).to_numpy()
    for tp in TPS:
        for sl in SLS:
            p, code = pnl_of(Z, "L", hz, tp, sl)
            for per in PER + ("ALL",):
                m = sel & ((E.per == per).to_numpy() if per != "ALL" else True)
                x = p[m]
                rows.append(dict(tp=tp, sl=sl, per=per, n=int(m.sum()), exp=x.mean(), win=(code[m] == 1).mean(),
                                 sl_hit=(code[m] == -1).mean(), rw_win=sl / (tp + sl)))
    Hm = pd.DataFrame(rows)
    Hm["win_minus_rw"] = Hm.win - Hm.rw_win
    Hm.round(4).to_csv(os.path.join(OUT, f"heatmap_long_{hz}_{'all_slots' if len(times) > 3 else '_'.join(t.replace(':', '') for t in times)}.csv"), index=False)
    return Hm


# ---------------------------------------------------------------- 4. fixed candidates, one trade per day
CANDS = [
    # name, rule, time, tp, sl  (all long, eod horizon, points)
    ("Náhodný long 09:30 · 1:1 (15/15)", "BASE", "09:30", 15, 15),
    ("Náhodný long 09:30 · 1:3 (10/30)", "BASE", "09:30", 10, 30),
    ("Náhodný long 09:30 · 1:10 (10/100)", "BASE", "09:30", 10, 100),
    ("Pokles 10 b. za hodinu → long 09:00 · 6/30", "DN_10", "09:00", 6, 30),
    ("Pokles 10 b. za hodinu → long 09:30 · 15/15", "DN_10", "09:30", 15, 15),
    ("Pokles 10 b. za hodinu → long 09:30 · 10/50", "DN_10", "09:30", 10, 50),
    ("Růst 10 b. za hodinu (Asie 22:00) → long · 10/150", "UP_10", "22:00", 10, 150),
    ("Pokles 5 b. v býčím trhu (01:00) → long · 20/150", "DN_5_BULL", "01:00", 20, 150),
    ("Gap −20 b. v býčím trhu → long 09:30 · 15/50", "GAPDN_20_BULL", "09:30", 15, 50),
    ("Gap −20 b. v býčím trhu → long 09:30 · 25/25", "GAPDN_20_BULL", "09:30", 25, 25),
]


def candidates(E, Z, bh_year):
    R = rule_masks(E, np.ones(len(E)))
    summ, yearly, dow, month, curves = [], {}, {}, {}, {}
    for name, rule, t, tp, sl in CANDS:
        p, code = pnl_of(Z, "L", "eod", tp, sl)
        m = R[rule] & (E.time == t).to_numpy()
        D = pd.DataFrame({"gday": E.gday[m].to_numpy(), "year": E.year[m].to_numpy(), "per": E.per[m].to_numpy(),
                          "dow": E.dow[m].to_numpy(), "month": E.month[m].to_numpy(), "p": p[m], "c": code[m]})
        eq = D.p.cumsum().to_numpy(); dd = eq - np.maximum.accumulate(np.r_[0, eq])[1:]
        sl_idx = np.flatnonzero(D.c.to_numpy() == -1)
        gaps = np.diff(np.r_[-1, sl_idx, len(D)]) - 1
        r = dict(strategie=name, pravidlo=rule, cas=t, tp=tp, sl=sl, obchodu=len(D), win=(D.c == 1).mean(),
                 rw_win=sl / (tp + sl), sl_zasahu=int((D.c == -1).sum()), exp=D.p.mean(), suma=D.p.sum(),
                 max_dd=dd.min() if len(dd) else 0, nejdelsi_bez_sl=int(gaps.max()) if len(gaps) else 0,
                 nejhorsi_obchod=D.p.min())
        for per in PER:
            x = D.p[D.per == per]
            r[f"exp_{per}"] = x.mean(); r[f"n_{per}"] = len(x)
            r[f"t_{per}"] = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan
        Yr = D.groupby("year").p.agg(["sum", "size"])
        Yr["bh"] = bh_year.reindex(Yr.index).to_numpy()
        r["let_ziskovych"] = int((Yr["sum"] > 0).sum()); r["let_nad_bh"] = int((Yr["sum"] > Yr.bh).sum()); r["let"] = len(Yr)
        summ.append(r)
        yearly[name] = Yr
        dow[name] = D.groupby("dow").p.agg(["mean", "size"])
        month[name] = D.groupby("month").p.agg(["mean", "size"])
        curves[name] = D[["gday", "p"]].assign(eq=eq)
    Sm = pd.DataFrame(summ)
    Sm.round(3).to_csv(os.path.join(OUT, "candidates_summary.csv"), index=False)
    Y = pd.concat({k: v["sum"] for k, v in yearly.items()}, axis=1)
    Y["B&H body"] = bh_year.reindex(Y.index)
    Y.round(1).to_csv(os.path.join(OUT, "candidates_yearly.csv"))
    Dw = pd.concat({k: v["mean"] for k, v in dow.items()}, axis=1); Dw.index = ["Po", "Út", "St", "Čt", "Pá"][:len(Dw)]
    Dw.round(2).to_csv(os.path.join(OUT, "candidates_dow.csv"))
    Mo = pd.concat({k: v["mean"] for k, v in month.items()}, axis=1)
    Mo.round(2).to_csv(os.path.join(OUT, "candidates_month.csv"))
    return Sm, Y, Dw, Mo, curves


def bh_points():
    import features as F
    T = F.load()["T"]
    C = T.C
    y = C.groupby(C.index.year).last()
    prev = y.shift(); prev.iloc[0] = C.iloc[0]
    return (y - prev), C


def main():
    os.makedirs(OUT, exist_ok=True)
    S, T, ref = selection()
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print(S.round(3).to_string()); print(ref)
    E, Z = load()
    H, Ha, YY = hour_map(E, Z)
    M = mae_before_tp(E, Z, 15)
    Hm = heatmap(E, Z, ("09:30",))
    Hall = heatmap(E, Z, tuple(sorted(E.time.unique())))
    bh_year, C = bh_points()
    Sm, Y, Dw, Mo, curves = candidates(E, Z, bh_year)
    print(Sm.round(2).to_string()); print(Y.round(0).to_string()); print(Dw.to_string()); print(YY.to_string())
    print(M.to_string())
    # ------------------------------------------------ data for the report
    def rec(df):
        return json.loads(df.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))
    bh_c = C.resample("W").last().dropna()
    bh_c = (bh_c - bh_c.iloc[0])
    data = dict(
        selection=rec(S), ref=ref, top=rec(T.round(3)),
        hour=rec(H[H.per != "ALL"].round(4)), hour_all=rec(H[H.per == "ALL"].round(4)), hour_atr=rec(Ha),
        p15_year=json.loads(YY.reset_index().to_json(orient="records")), mae=rec(M.round(3)),
        heat930=rec(Hm.round(3)), heatall=rec(Hall.round(3)),
        cand=rec(Sm.round(3)), yearly=json.loads(Y.round(1).reset_index().to_json(orient="records")),
        dow=json.loads(Dw.round(2).reset_index().to_json(orient="records")),
        month=json.loads(Mo.round(2).reset_index().to_json(orient="records")),
        curves={k: dict(d=[str(x)[:10] for x in v.gday.to_numpy()[::3]], e=np.round(v["eq"].to_numpy()[::3], 1).tolist())
                for k, v in curves.items()},
        bh=dict(d=[str(x)[:10] for x in bh_c.index], e=np.round(bh_c.to_numpy(), 1).tolist()),
    )
    json.dump(data, open(os.path.join(OUT, "report_data.json"), "w"), ensure_ascii=False)
    print("saved")


if __name__ == "__main__":
    main()
