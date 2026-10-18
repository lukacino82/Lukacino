"""Collect the Regime Atlas results into out/report.html."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# what happened on ES in each year (only well documented events; 2026 is described from the data only)
EVENTS = {
    2009: "Dno finanční krize v březnu, QE1 a prudká rally z extrémně přeprodaného trhu.",
    2010: "Flash crash v květnu a dluhová krize eurozóny (korekce ~16 %), od léta QE2 a návrat trendu.",
    2011: "Dluhový strop a snížení ratingu USA v srpnu, eurokrize: panický pokles a vysoká volatilita, rok skončil na nule.",
    2012: "Eurokrize odeznívá („whatever it takes“, QE3), mírný trend s jednou korekcí na jaře.",
    2013: "Nejklidnější silný trend dekády, krátké zakolísání při „taper tantrum“ v létě.",
    2014: "Klidný růst, krátký říjnový výprodej s rychlým návratem.",
    2015: "Stranový rok, v srpnu devalvace jüanu a bleskový výprodej.",
    2016: "Leden–únor pokles (Čína, ropa), Brexit v červnu, od listopadu „Trump rally“.",
    2017: "Rekordně nízká volatilita a téměř nepřerušený trend nahoru.",
    2018: "Únorový „Volmageddon“, ve 4. čtvrtletí výprodej −16 % (utahování Fedu, obchodní válka).",
    2019: "Obrat Fedu, strmý návrat z prosincového dna, letní zakolísání kvůli obchodní válce.",
    2020: "Covidový krach −28 % za měsíc a nejrychlejší V-návrat v historii díky stimulům.",
    2021: "Stimuly a nízké sazby: klidný a silný trend, spekulativní mánie.",
    2022: "Inflace a nejrychlejší zvyšování sazeb: medvědí trh −20 % s ostrými protipohyby.",
    2023: "Krize regionálních bank (SVB) v březnu, AI rally, podzimní korekce (výnosy 5 %), silný konec roku.",
    2024: "AI trend, v srpnu prudký skok volatility (unwind jenového carry trade) a rychlý návrat.",
    2025: "Clové šoky: pokles v 1. čtvrtletí, dubnový krach a strmý V-návrat, pak klidný trend.",
    2026: "Podle dat: korekce ~10 % v 1. čtvrtletí, strmý růst ve 2. čtvrtletí (+13 %), klidnější 3. čtvrtletí.",
}


def r(x, d=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    return None if not np.isfinite(x) else round(x, d)


def recs(df, d=4):
    return [{k: (r(v, d) if not isinstance(v, str) else v) for k, v in row.items()} for row in df.to_dict("records")]


def main():
    SM = pd.read_csv(os.path.join(OUT, "summary.csv"))
    Q = pd.read_csv(os.path.join(OUT, "quarters.csv"))
    YX = pd.read_csv(os.path.join(OUT, "y_excess.csv")).set_index("date")
    QX = pd.read_csv(os.path.join(OUT, "q_excess.csv")); QX = QX.set_index(QX.columns[0])
    LB = pd.read_csv(os.path.join(OUT, "by_label.csv"))
    RG = pd.read_csv(os.path.join(OUT, "by_regime.csv"))
    RO = pd.read_csv(os.path.join(OUT, "rolling_alpha.csv"), index_col=0, parse_dates=True)
    YB = pd.read_csv(os.path.join(OUT, "bh_years.csv")).set_index("date").iloc[:, 0]
    R = pd.read_parquet(os.path.join(OUT, "returns.parquet"))
    bh = R["B&H"]
    eq = (1 + bh).cumprod()
    w = eq.resample("W").last()
    years = []
    for y, x in bh.groupby(bh.index.year):
        e = (1 + x).cumprod()
        qs = Q[Q.q.str.startswith(str(y))]
        years.append(dict(year=int(y), ret=r((1 + x).prod() - 1), mdd=r((e / e.cummax() - 1).min()), vol=r(x.std() * np.sqrt(252)),
                          labels=list(qs.label), event=EVENTS.get(int(y), ""),
                          best=[c for c, v in YX.loc[y].sort_values(ascending=False).head(3).items()],
                          beat=int((YX.loc[y] > 0).sum())))
    order = list(SM.sort_values(["family", "alpha"], ascending=[True, False]).strategy)
    data = dict(
        summary=recs(SM), order=order, quarters=recs(Q), years=years,
        yx={c: [r(v) for v in YX[c]] for c in YX.columns}, yidx=[int(i) for i in YX.index],
        qx={c: [r(v) for v in QX[c]] for c in QX.columns}, qidx=list(QX.index),
        bylabel=recs(LB), byregime=recs(RG),
        roll={c: [[d.strftime("%Y-%m"), r(v)] for d, v in RO[c].dropna().items()] for c in RO.columns},
        bheq=[[d.strftime("%Y-%m-%d"), r(v, 3)] for d, v in w.items()],
        kpi=dict(n=len(SM), quarters=len(Q), down_years=int((YB < 0).sum()), years=len(YB),
                 sig=int((SM.t_alpha >= 1.96).sum()), neg=int((SM.t_alpha <= -1.96).sum())),
    )
    tpl = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    print("report", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
