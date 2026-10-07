"""Collect the results into out/report.html (self-contained)."""
from __future__ import annotations

import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from base import summarize  # noqa: E402
from families import (Grid, bh, crisis_allocator, exposure_overlays, hour_bias_wf, hour_table,  # noqa: E402,F401
                      intraday_momentum, noise_momentum, overnight, pre_fomc, pre_holiday, opex_week, rth_only,
                      turn_of_month, ibs_bull)

D = "/tmp/claude-0/data/"
OUT = os.path.join(HERE, "out")
PER = [("PRE", "2008", "2017-12-31"), ("IS", "2018", "2022-12-31"), ("OOS", "2023", "2027")]


def r2(x, d=2):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def sr(x):
    return r2(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else None


def perf(x):
    eq = (1 + x).cumprod()
    yrs = len(x) / 252
    c = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    return dict(cagr=r2(c * 100), sr=sr(x), dd=r2(dd * 100, 1), vol=r2(x.std() * np.sqrt(252) * 100, 1))


def alpha_t(x, b):
    X = np.c_[np.ones(len(b)), b.values]
    be = np.linalg.lstsq(X, x.values, rcond=None)[0]
    res = x.values - X @ be
    return r2(be[0] / np.sqrt(res.var(ddof=2) / len(x))), r2(be[1]), r2(be[0] * 252 * 100)


def curve(x, freq="W-FRI"):
    eq = (1 + x).cumprod().resample(freq).last().dropna()
    return [[d.strftime("%Y-%m-%d"), r2(v, 3)] for d, v in eq.items()]


def main():
    G = pickle.load(open(D + "m_grid.pkl", "rb"))
    res = pickle.load(open(D + "m_res1.pkl", "rb"))
    df = pd.read_parquet(D + "daily_series.parquet")
    r = df["B&H"]

    # ---- Mattia strategies: per period stats + equity in points
    names = {"S1": "Vault Break (long, 30 min)", "S2": "VWAP Pullback + ADX (long, 1 min)",
             "S3": "Overnight Bias ORB (L/S, 15 min)"}
    mattia = []
    for k, t in res.items():
        s = summarize(t)
        g = summarize(t, 0.0)
        eqp = (t.pnl - 0.5).cumsum()
        mattia.append(dict(key=k, name=names[k], n=s["ALL"]["n"], exp=r2(s["ALL"]["exp"]), pf=r2(s["ALL"]["pf"]),
                           win=r2(s["ALL"]["win"] * 100, 0), dd=r2(s["ALL"]["maxdd"], 0), net=r2(s["ALL"]["net"], 0),
                           gross=r2(g["ALL"]["exp"]),
                           per=[r2(s[p]["exp"]) if s[p].get("n") else None for p in ("PRE 2008-17", "IS 2018-22", "OOS 2023-26")],
                           pern=[s[p].get("n", 0) for p in ("PRE 2008-17", "IS 2018-22", "OOS 2023-26")],
                           eq=[[d.strftime("%Y-%m-%d"), r2(v, 1)] for d, v in zip(t.date, eqp)][::2]))
    s3 = res["S3"]
    s3_long = summarize(s3[s3.side > 0]); s3_short = summarize(s3[s3.side < 0])
    side = dict(long=[r2(s3_long[p].get("exp")) for p in ("PRE 2008-17", "IS 2018-22", "OOS 2023-26")],
                short=[r2(s3_short[p].get("exp")) for p in ("PRE 2008-17", "IS 2018-22", "OOS 2023-26")])

    # ---- hour of day (video 2)
    ht = hour_table(G)
    hours = [dict(h=c, all=r2(ht[c].mean() * 1e4), pre=r2(ht[c][:"2017"].mean() * 1e4),
                  post=r2(ht[c]["2018":].mean() * 1e4)) for c in ht.columns if c != "16:00"]
    # 16:00-17:00 ET straddles the old 16:15-16:30 halt and the 17:00 close; too few clean marks

    # ---- families table
    fam_defs = [
        ("Buy & hold ES", r, "benchmark", "—"),
        ("Overnight drift 16:00→09:30 (hrubě)", overnight(G, 0), "čas", "beta"),
        ("Overnight drift po nákladech", overnight(G), "čas", "no"),
        ("Hodinová sezónnost, walk-forward (video 2), hrubě", hour_bias_wf(G, cost=0)[0], "čas", "no"),
        ("Hodinová sezónnost, walk-forward, po nákladech", hour_bias_wf(G)[0], "čas", "no"),
        ("Intradenní momentum (Gao 2018)", intraday_momentum(G), "momentum", "no"),
        ("Noise-area momentum L/S, hrubě", noise_momentum(G, cost=0)[0], "momentum", "watch"),
        ("Noise-area momentum L/S, po nákladech", df["Noise-area momentum L/S"], "momentum", "watch"),
        ("Mattia S1 Vault Break", df["S1 Vault Break"], "momentum", "no"),
        ("Mattia S2 VWAP Pullback", df["S2 VWAP Pullback"], "mean reversion", "no"),
        ("Mattia S3 Overnight Bias", df["S3 Overnight Bias"], "momentum", "watch"),
        ("Turn of month", df["Turn of month"], "kalendář", "beta"),
        ("Pre-FOMC 24 h (2016+)", pre_fomc(G), "kalendář", "watch"),
        ("Pre-holiday", pre_holiday(G), "kalendář", "no"),
        ("OPEX week", opex_week(G), "kalendář", "no"),
        ("IBS < 0,2 v bull režimu, 1 den", df["IBS<0.2 bull"], "mean reversion", "no"),
        ("Vol-managed B&H (cíl = vol B&H, max 2×)", df["Vol-managed B&H"], "expozice", "go"),
        ("Trend filtr MA200 (0/1)", exposure_overlays(G)["Trend filter MA200 (0/1)"][0] * r, "expozice", "go"),
        ("Crisis allocator (−3 %, 0,5×, 2 vrstvy)", df["Crisis allocator (-3%, 0.5x, 2 vrstvy)"], "expozice", "watch"),
    ]
    fams = []
    for name, x, grp, v in fam_defs:
        x = x.dropna()
        b = r.reindex(x.index)
        at, beta, aa = alpha_t(x, b) if name != "Buy & hold ES" else (None, 1.0, 0.0)
        p = perf(x)
        fams.append(dict(name=name, grp=grp, verdict=v, ann=r2(x.mean() * 252 * 100), sr=sr(x), alpha=aa, at=at,
                         beta=beta, dd=p["dd"], expo=r2((x != 0).mean() * 100, 0),
                         per=[sr(x[a:z]) if len(x[a:z]) > 100 else None for _, a, z in PER]))

    # ---- allocator fairness
    w = crisis_allocator(G, dd_thr=-0.03, ll=3, layer=0.5, hold=60, max_layers=2).shift().fillna(1)
    aw = w.mean()
    vm_w = exposure_overlays(G)["Vol-managed B&H (cap 2x)"][0]
    alloc = dict(avg_w=r2(aw), curves=dict(alloc=curve(w * r), lev=curve(aw * r), vm=curve((vm_w * aw / vm_w.mean()) * r),
                                           bh=curve(r)),
                 stats=dict(alloc=perf(w * r), lev=perf(aw * r), vm=perf((vm_w * aw / vm_w.mean()) * r), bh=perf(r)))
    ag = pd.read_csv(os.path.join(OUT, "alloc_grid.csv"))
    alloc["grid"] = dict(n=len(ag), mean_at=r2(ag.alpha_t.mean()), share_all=r2(((ag["PRE_exc%"] > 0) & (ag["IS_exc%"] > 0) & (ag["OOS_exc%"] > 0)).mean() * 100, 0),
                         by_dd=ag.groupby("dd")[["alpha_t", "PRE_exc%", "IS_exc%", "OOS_exc%"]].mean().round(2).reset_index().to_dict("records"))

    # ---- books
    book = df["Vol-managed B&H"] + df["Noise-area momentum L/S"] + df["S3 Overnight Bias"] + df["Pre-FOMC"]
    books = {}
    for k, x in {"bh": r, "vm": df["Vol-managed B&H"], "book": book,
                 "alloc_book": df["Crisis allocator (-3%, 0.5x, 2 vrstvy)"] + df["Noise-area momentum L/S"] + df["S3 Overnight Bias"],
                 "mattia": df["S1 Vault Break"] + df["S2 VWAP Pullback"] + df["S3 Overnight Bias"]}.items():
        p = perf(x)
        p["per"] = [sr(x[a:z]) for _, a, z in PER]
        sc = x.std() / r.std()
        p["bh_same_vol"] = perf(r * sc)
        p["curve"] = curve(x)
        books[k] = p
    books["bh_book_vol"] = dict(curve=curve(r * (book.std() / r.std())))
    corr_keys = ["B&H", "Vol-managed B&H", "Crisis allocator (-3%, 0.5x, 2 vrstvy)", "S1 Vault Break", "S3 Overnight Bias",
                 "Noise-area momentum L/S", "Turn of month", "Pre-FOMC"]
    corr = df[corr_keys].corr().round(2)

    # ---- prop sim (text table from run8)
    prop = open(os.path.join(OUT, "run8.txt")).read()

    ng = pd.read_csv(os.path.join(OUT, "noise_grid.csv"))
    noise_cost = ng.groupby("cost").ALL.agg(["mean", "max"]).round(2).reset_index().to_dict("records")

    data = dict(mattia=mattia, side=side, hours=hours, fams=fams, alloc=alloc, books=books,
                corr=dict(keys=corr_keys, m=corr.values.tolist()), prop=prop, noise_cost=noise_cost)
    tpl = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    print("report", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
