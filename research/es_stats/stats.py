"""Block 1 - descriptive statistics of ES / S&P (2010-01 .. 2026-09).
Percent figures come from the reconstructed S&P cash series (1 minute, ET); point figures from ES back-adjusted.
A  hours: range, return, P(up), volume for every hour of the day and weekday (and per year)
B  weekdays: return, P(up), sell-off / rally frequency, range, choppiness, per year
C  periods (year / month / week): return %, max drawdown inside the period %, open-to-low %, ratio
D  weekly drawdown distribution per year (percentiles) -> what share of the account survives which drop
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

DATA = "/tmp/claude-0/data"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
START, END = "2010-01-01", "2026-09-26"
WD = ["Po", "Ut", "St", "Ct", "Pa", "So", "Ne"]


def cash():
    c = pd.read_parquet(os.path.join(DATA, "bcl_cash.parquet"))
    c = c[(c.ts >= START) & (c.ts < END)].reset_index(drop=True)
    c["gday"] = (c.ts + pd.Timedelta(hours=6)).dt.normalize()
    return c


def es():
    d = pd.read_parquet(os.path.join(DATA, "rrr", "bars.parquet"))
    return d[(d.ts >= START) & (d.ts < END)].reset_index(drop=True)


def part_A(c, d):
    """hourly bars: range in points (ES) and % (cash), return, P(up), volume"""
    h = d.set_index("ts").resample("1h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                              "Volume": "sum", "delta": "sum"}).dropna()
    hc = c.set_index("ts").resample("1h").agg({"O": "first", "H": "max", "L": "min", "C": "last"}).dropna()
    h = h.join(hc, how="inner")
    h["rozpeti_b"] = h.High - h.Low
    h["rozpeti_pct"] = (h.H - h.L) / h.O * 100
    h["vynos_pct"] = (h.C - h.O) / h.O * 100
    h["nahoru"] = h.C > h.O
    h["hodina"] = h.index.hour
    gd = (h.index + pd.Timedelta(hours=6)).normalize()
    h["den"] = [WD[x] for x in gd.day_of_week]
    h["rok"] = gd.year
    agg = dict(n=("vynos_pct", "size"), rozpeti_b=("rozpeti_b", "mean"), rozpeti_pct=("rozpeti_pct", "mean"),
               vynos_pct=("vynos_pct", "mean"), p_nahoru=("nahoru", "mean"), objem=("Volume", "mean"),
               delta=("delta", "mean"))
    a1 = h.groupby("hodina").agg(**agg)
    a2 = h.groupby(["den", "hodina"]).agg(**agg).reset_index()
    a3 = h.groupby(["rok", "hodina"]).agg(**agg).reset_index()
    # sum of up and down moves per hour (long vs short potential): mean max excursion up / down from the open
    h["nahoru_b"] = h.High - h.Open; h["dolu_b"] = h.Open - h.Low
    a4 = h.groupby(["den", "hodina"]).agg(nahoru_b=("nahoru_b", "mean"), dolu_b=("dolu_b", "mean"),
                                          vynos_pct=("vynos_pct", "mean"), p_nahoru=("nahoru", "mean")).reset_index()
    a1.round(4).to_csv(os.path.join(OUT, "A1_hodiny.csv"))
    a2.round(4).to_csv(os.path.join(OUT, "A2_den_hodina.csv"), index=False)
    a3.round(4).to_csv(os.path.join(OUT, "A3_rok_hodina.csv"), index=False)
    a4.round(4).to_csv(os.path.join(OUT, "A4_den_hodina_long_short.csv"), index=False)
    return h


def daily_cash(c):
    """RTH day 09:30-16:00 ET and Globex day; close-to-close return uses the 16:00 close"""
    r = c[(c.ts.dt.time >= pd.Timestamp("09:30").time()) & (c.ts.dt.time < pd.Timestamp("16:00").time())]
    g = r.groupby(r.ts.dt.normalize()).agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"))
    g["ret"] = g.C.pct_change() * 100
    g["rth_ret"] = (g.C / g.O - 1) * 100
    g["rozpeti_pct"] = (g.H - g.L) / g.O * 100
    g["eff"] = (g.C - g.O).abs() / (g.H - g.L)          # 1 = trend day, near 0 = choppy
    g["den"] = [WD[x] for x in g.index.day_of_week]
    g["rok"] = g.index.year
    return g.dropna()


def part_B(g):
    q10 = g.groupby("rok").ret.transform(lambda x: x.quantile(0.1))
    q90 = g.groupby("rok").ret.transform(lambda x: x.quantile(0.9))
    g = g.assign(vyprodej=g.ret <= q10, rally=g.ret >= q90, pokles1=g.ret <= -1, pokles2=g.ret <= -2,
                 rust1=g.ret >= 1, choppy=(g.eff < 0.25) & (g.rozpeti_pct < g.groupby("rok").rozpeti_pct.transform("median")))
    agg = dict(dnu=("ret", "size"), vynos_pct=("ret", "mean"), median_pct=("ret", "median"), p_rust=("ret", lambda x: (x > 0).mean()),
               vyprodej_10pct=("vyprodej", "mean"), rally_10pct=("rally", "mean"), pokles_pod_1pct=("pokles1", "mean"),
               pokles_pod_2pct=("pokles2", "mean"), rust_nad_1pct=("rust1", "mean"), rozpeti_pct=("rozpeti_pct", "mean"),
               efektivita=("eff", "mean"), choppy_podil=("choppy", "mean"))
    b1 = g.groupby("den").agg(**agg).reindex(WD[:5])
    b2 = g.groupby(["rok", "den"]).agg(**agg).reset_index()
    b1.round(4).to_csv(os.path.join(OUT, "B1_dny.csv"))
    b2.round(4).to_csv(os.path.join(OUT, "B2_rok_den.csv"), index=False)
    # best / worst weekday per year
    piv = b2.pivot(index="rok", columns="den", values="vynos_pct")[WD[:5]]
    best = pd.DataFrame({"nejlepsi_den": piv.idxmax(1), "vynos_nejlepsi": piv.max(1),
                         "nejhorsi_den": piv.idxmin(1), "vynos_nejhorsi": piv.min(1)})
    pv = b2.pivot(index="rok", columns="den", values="vyprodej_10pct")[WD[:5]]
    best["nejvic_vyprodeju"] = pv.idxmax(1)
    pr = b2.pivot(index="rok", columns="den", values="rozpeti_pct")[WD[:5]]
    best["nejmensi_rozpeti"] = pr.idxmin(1)
    best.round(3).to_csv(os.path.join(OUT, "B3_nejlepsi_den_rok.csv"))
    return g


def periods(c, rule):
    """per period: return %, max drawdown inside the period (1-minute path, from running high), open-to-low %"""
    s = c.set_index("ts")
    key = {"Y": s.index.year, "M": s.index.to_period("M"),
           "W": ((s.index + pd.Timedelta(hours=6)).normalize() - pd.to_timedelta(
               (s.index + pd.Timedelta(hours=6)).normalize().day_of_week, unit="D"))}[rule]
    rows = []
    for k, g in s.groupby(key):
        hi = np.maximum.accumulate(g.H.to_numpy())
        dd = (g.L.to_numpy() / hi - 1).min() * 100
        o = g.O.iloc[0]; cl = g.C.iloc[-1]
        up = (np.maximum.accumulate(g.H.to_numpy())[-1] / o - 1) * 100
        rows.append(dict(obdobi=str(k)[:10], vynos_pct=(cl / o - 1) * 100, max_propad_pct=dd,
                         open_k_low_pct=(g.L.min() / o - 1) * 100, open_k_high_pct=up))
    p = pd.DataFrame(rows)
    p["pomer_vynos_propad"] = p.vynos_pct / p.max_propad_pct.abs().replace(0, np.nan)
    return p


def part_CD(c):
    out = {}
    for rule, name in (("Y", "roky"), ("M", "mesice"), ("W", "tydny")):
        p = periods(c, rule)
        p.round(3).to_csv(os.path.join(OUT, f"C_{name}.csv"), index=False)
        out[rule] = p
    w = out["W"].copy(); w["rok"] = w.obdobi.str[:4].astype(int)
    q = w.groupby("rok").max_propad_pct.describe(percentiles=[0.5, 0.75, 0.9, 0.95, 0.99])
    q["prumer_vynos_tyden"] = w.groupby("rok").vynos_pct.mean()
    q["podil_tydnu_propad_nad_3pct"] = w.groupby("rok").max_propad_pct.apply(lambda x: (x <= -3).mean())
    q["podil_tydnu_propad_nad_5pct"] = w.groupby("rok").max_propad_pct.apply(lambda x: (x <= -5).mean())
    q.round(3).to_csv(os.path.join(OUT, "D1_tydenni_propady_rok.csv"))
    m = out["M"].copy(); m["rok"] = m.obdobi.str[:4].astype(int)
    qm = m.groupby("rok").max_propad_pct.describe(percentiles=[0.5, 0.9])
    qm["prumer_vynos_mesic"] = m.groupby("rok").vynos_pct.mean()
    qm.round(3).to_csv(os.path.join(OUT, "D2_mesicni_propady_rok.csv"))
    # survival table: share of weeks / months whose drawdown stays above -x %
    rows = []
    for x in (1, 2, 3, 4, 5, 7, 10, 15, 20, 30):
        rows.append(dict(propad_pct=x, tydnu_mensi=(out["W"].max_propad_pct > -x).mean(),
                         mesicu_mensi=(out["M"].max_propad_pct > -x).mean(),
                         roku_mensi=(out["Y"].max_propad_pct > -x).mean()))
    pd.DataFrame(rows).round(4).to_csv(os.path.join(OUT, "D3_preziti_propadu.csv"), index=False)
    return out


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    c = cash(); d = es()
    part_A(c, d); print("A", flush=True)
    part_B(daily_cash(c)); print("B", flush=True)
    part_CD(c); print("CD", flush=True)
